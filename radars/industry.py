from __future__ import annotations
import logging
from pathlib import Path
import httpx
from radar.config import get_settings
from radar.schema import Event
from collectors.rss import RSSCollector
from collectors.defillama import DefiLlamaCollector
from collectors.coingecko import CoinGeckoCollector
from collectors.base import collect_all
from pipeline.filter import filter_events
from pipeline.dedupe import dedupe
from pipeline.cluster import cluster_events
from pipeline.score import apply_score
from pipeline.analyze import analyze_events
from pipeline.cost_guard import CostGuard
from pipeline.openai_client import OpenAIClient
from storage.store import append_events

logger = logging.getLogger(__name__)

def build_collectors(settings: dict) -> list:
    sources = settings["sources"].get("industry",{})
    scoring = settings["scoring"]
    collectors = []
    for grp in ["official_primary","established_media"]:
        for s in sources.get(grp,[]):
            collectors.append(RSSCollector(name=s["name"], url=s["url"], radar="industry", credibility=s.get("credibility",70)))
    for s in sources.get("defi_data",[]):
        if s["type"] == "defillama":
            collectors.append(DefiLlamaCollector(credibility=s.get("credibility",90)))
        elif s["type"] == "coingecko":
            collectors.append(CoinGeckoCollector(credibility=s.get("credibility",80)))
    return collectors

async def run_industry_scan(client: httpx.AsyncClient, settings: dict, guard: CostGuard | None = None, ai_client: OpenAIClient | None = None, do_ai: bool = True, seen: set | None = None) -> dict:
    collectors = build_collectors(settings)
    results = await collect_all(collectors, client)
    all_events: list[Event] = []
    failed = 0
    for r in results:
        if not r.success:
            failed += 1
        all_events.extend(r.events)
    # Cross-run dedupe via persistent seen set
    if seen:
        all_events = [e for e in all_events if e.event_id not in seen]
    raw = len(all_events)
    # Pipeline
    scoring_cfg = settings["scoring"]
    noise_kw = scoring_cfg.get("noise_keywords",[])
    kept, noise_removed = filter_events(all_events, noise_kw)
    deduped, dedup_stats = dedupe(kept, fuzzy_threshold=scoring_cfg.get("fuzzy_threshold",88))
    clustered = cluster_events(deduped)
    # Heuristic scoring before AI (set defaults)
    for e in clustered:
        e.impact = 60 if e.credibility >= 85 else 50
        e.wallet_relevance = 55
        e.novelty = 50
    scored = apply_score(clustered, "industry", scoring_cfg)

    # AI classification (optional)
    ai_calls_before = guard.calls_this_run if guard else 0
    if do_ai and ai_client and ai_client.available() and guard:
        models = settings["models"]
        # filter to candidates (score >=40) to save cost
        candidates = [e for e in scored if e.score >= 40]
        # cap per run
        max_input = models.get("max_weekly_input_events",80)
        candidates = sorted(candidates, key=lambda x: x.score, reverse=True)[:max_input]
        if candidates:
            analyze_events(candidates, "industry", ai_client, guard, models)
            # re-score after AI updates dimensions
            scored = apply_score(scored, "industry", scoring_cfg)

    # Only persist non-noise? Save weekly+ important+ critical
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
