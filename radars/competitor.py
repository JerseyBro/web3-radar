from __future__ import annotations
import logging
from pathlib import Path
import httpx
from radar.config import get_settings
from radar.schema import Event
from collectors.rss import RSSCollector
from collectors.github import GitHubCollector
from collectors.app_store import AppStoreCollector
from collectors.google_play import GooglePlayCollector
from collectors.base import collect_all
from pipeline.filter import filter_events
from pipeline.dedupe import dedupe
from pipeline.cluster import cluster_events
from pipeline.score import apply_score
from pipeline.analyze import analyze_events
from pipeline.cost_guard import CostGuard
from pipeline.openai_client import OpenAIClient
from storage.store import append_events
from storage.state import StateStore

logger = logging.getLogger(__name__)

def build_collectors(settings: dict, state: StateStore | None = None) -> list:
    wallets = settings["sources"].get("competitor",{}).get("wallets",[])
    resolved = state.load_resolved() if state else {}
    collectors = []
    for w in wallets:
        name = w["name"]
        slug = w["slug"]
        # Blog RSS (try generic feed URLs)
        blog = w.get("blog","")
        if blog:
            # Try RSS variants; we use direct blog url as rss fallback via RSS collector (will fail gracefully)
            collectors.append(RSSCollector(name=f"{name} Blog", url=blog+"/rss.xml", radar="competitor", credibility=80))
            collectors.append(RSSCollector(name=f"{name} Blog", url=blog+"/feed", radar="competitor", credibility=80))
        # GitHub
        gh = w.get("github","")
        if gh:
            # parse repo: if multiple, pick first; also handle org
            # For orgs, we need to pick likely main repo? Use heuristic: wallet name
            # Collect releases from org's likely repo: try constructing <org>/<slug>
            # Actually try to fetch releases from the org's pinned? Simplistic: use org as repo placeholder and let collector handle 404
            # Better: if github is org URL (no repo), try to collect from likely repos via GitHub API search later; for now, try common names
            parts = gh.rstrip("/").split("/")
            if len(parts) >= 4 and gh.count("/") >= 4:  # has repo
                repo = "/".join(parts[-2:])
                collectors.append(GitHubCollector(name=name, repo=repo, credibility=85))
            else:
                # org only: try slug variants
                org = parts[-1]
                for repo_name in [slug, slug.replace("-",""), "wallet", "app"]:
                    collectors.append(GitHubCollector(name=name, repo=f"{org}/{repo_name}", credibility=75))
        # App Store
        app_id = None
        if slug in resolved:
            app_id = resolved[slug].get("app_store",{}).get("app_id")
        collectors.append(AppStoreCollector(name=name, app_id=app_id, app_name=w.get("app_store_name")))
        # Google Play
        pkg = w.get("google_play_id")
        collectors.append(GooglePlayCollector(name=name, package_id=pkg))
    return collectors

async def run_competitor_scan(client: httpx.AsyncClient, settings: dict, guard: CostGuard | None = None, ai_client: OpenAIClient | None = None, do_ai: bool = True, state: StateStore | None = None, seen: set | None = None) -> dict:
    collectors = build_collectors(settings, state)
    results = await collect_all(collectors, client)
    all_events: list[Event] = []
    failed = 0
    for r in results:
        if not r.success:
            failed += 1
        # filter empty app store unresolved etc not counted as failed if success True
        all_events.extend(r.events)
    if seen:
        all_events = [e for e in all_events if e.event_id not in seen]
    raw = len(all_events)
    scoring_cfg = settings["scoring"]
    noise_kw = scoring_cfg.get("noise_keywords",[])
    kept, noise_removed = filter_events(all_events, noise_kw)
    deduped, dedup_stats = dedupe(kept, fuzzy_threshold=scoring_cfg.get("fuzzy_threshold",88))
    clustered = cluster_events(deduped)
    for e in clustered:
        e.strategic_importance = 50
        e.wallet_relevance = 60
        e.novelty = 50
        e.execution_signal = 50
        e.credibility = e.credibility or 60
    scored = apply_score(clustered, "competitor", scoring_cfg)

    ai_calls_before = guard.calls_this_run if guard else 0
    if do_ai and ai_client and ai_client.available() and guard:
        models = settings["models"]
        candidates = [e for e in scored if e.score >= 40]
        max_input = models.get("max_weekly_input_events",80)
        candidates = sorted(candidates, key=lambda x: x.score, reverse=True)[:max_input]
        if candidates:
            analyze_events(candidates, "competitor", ai_client, guard, models)
            scored = apply_score(scored, "competitor", scoring_cfg)

    to_store = [e for e in scored if e.tier in ("weekly","important","critical")]
    if to_store:
        append_events(to_store)

    return {
        "sources_checked": len(collectors),
        "sources_failed": failed,
        "raw_items": raw,
        "duplicates_removed": dedup_stats["total_removed"],
        "noise_removed": len(noise_removed),
        "candidate_events": len(scored),
        "ai_calls": (guard.calls_this_run - ai_calls_before) if guard else 0,
        "events": scored,
        "processed_ids": [e.event_id for e in scored],
        "critical_events": [e for e in scored if e.tier=="critical"],
    }
