from __future__ import annotations
import asyncio
import argparse
import os
import logging
import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
import httpx

from radar.config import get_settings, ROOT
from pipeline.cost_guard import CostGuard
from pipeline.llm import LLMClient
from pipeline.llm.registry import resolve_role
from pipeline.analyze import synthesize_report
from storage.state import StateStore
from storage.store import (
    is_new_critical, mark_critical_alerted, report_path as _store_report_path,
)
from storage import git_state
from outputs.router import OutputRouter
from outputs.base import DeliveryContext, DeliveryStatus
from radar.report import Report, build_solo_report, public_source_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("radar")

WEEK = datetime.now(timezone.utc).strftime("%Y-W%V")


def make_guard(settings, state: StateStore) -> CostGuard:
    models = settings["models"]
    return CostGuard(
        state=state,
        budget_usd=float(models.get("monthly_ai_budget_usd", 5)),
        max_calls_per_run=int(models.get("max_ai_calls_per_run", 20)),
        pricing=models.get("pricing", {}),
    )

def make_client(settings) -> LLMClient:
    return LLMClient(settings["models"])

def period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-W%V")


def report_run_url() -> str | None:
    """Link only to the current GitHub Actions run when its identity is valid."""
    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        return None
    if any(part in (".", "..") for part in repo.split("/")) or not re.fullmatch(r"[0-9]+", run_id):
        return None
    return f"https://github.com/{repo}/actions/runs/{run_id}"


def critical_is_new(state: StateStore | None, event_id: str) -> bool:
    if state is not None and hasattr(state, "is_new_critical"):
        return state.is_new_critical(event_id)
    return is_new_critical(event_id)


def record_critical_alert(state: StateStore | None, event_id: str) -> None:
    if state is not None and hasattr(state, "mark_critical_alerted"):
        state.mark_critical_alerted(event_id)
        state.record_delivery("lark", event_id, "ok")
    else:
        mark_critical_alerted(event_id)


def build_report(radar: str, res: dict, settings, client, guard, no_ai: bool) -> Report:
    events = res["events"]
    report_events = [e for e in events if e.tier in ("weekly", "important", "critical")]
    report_events = sorted(report_events, key=lambda x: x.score, reverse=True)[:30]
    archive_candidates = [e for e in events if e.tier == "archive"]
    candidate_only = not report_events and bool(archive_candidates)
    if candidate_only:
        report_events = sorted(archive_candidates, key=lambda x: x.score, reverse=True)[:3]
    models = settings["models"]
    report_period = period()
    markdown = None
    synthesis_enabled = (settings.get("runtime") or {}).get("report", {}).get("synthesis_enabled", False)
    if (report_events and not candidate_only and synthesis_enabled and not no_ai
            and resolve_role(models, "synthesis").get("primary") and client.available()):
        prompt_path = ROOT / "prompts" / f"{radar}.md"
        markdown = synthesize_report(radar, report_events, client, guard, models, prompt_path)
    if not markdown:
        markdown = build_solo_report(
            radar, report_period, report_events,
            sources_checked=res.get("sources_checked", 0),
            sources_failed=res.get("sources_failed", 0),
            empty_reason=res.get("empty_reason"),
            candidate_only=candidate_only,
            cached_count=res.get("cached_events_added", 0),
        )
    meta = {
        "ai_cost_usd": round(guard.cost_this_run, 4),
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "sources_checked": res.get("sources_checked", 0),
        "sources_failed": res.get("sources_failed", 0),
        "collected": res.get("collected", 0),
        "high_signal": res.get("high_signal", 0),
        "empty_reason": res.get("empty_reason"),
        "candidate_only": candidate_only,
        "cached_events_added": res.get("cached_events_added", 0),
        "analysis_mode": "ai" if res.get("ai_calls", 0) > 0 else "rules",
    }
    if url := report_run_url():
        meta["report_url"] = url
    return Report(
        radar=radar, period=report_period, kind="weekly", events=report_events,
        markdown=markdown,
        meta=meta,
    )

def build_fallback_report(radar: str, events: list) -> str:
    lines = [f"# {radar.capitalize()} Weekly Report - {period()}", ""]
    if not events:
        lines.append("本周无高信号事件。")
        return "\n".join(lines)
    lines.append(f"共 {len(events)} 个信号事件。")
    lines.append("")
    for e in events[:15]:
        lines.append(f"- **{e.title}** (score:{e.score} tier:{e.tier})")
        lines.append(f"  - {e.ai_summary or e.excerpt[:200]}")
        lines.append(f"  - Source: {public_source_url(e.source_url) or '来源链接不可用'}")
    return "\n".join(lines)

def print_summary(label: str, res: dict, guard: CostGuard):
    s = guard.summary()
    warn = guard.warning()
    tail = f" | WARN: {warn}" if warn else ""
    # New observability: window + seen + high_signal
    collected = res.get("collected", res.get("raw_items", 0))
    after_window = res.get("after_window", collected)
    removed_by_window = res.get("removed_by_window", 0)
    after_seen = res.get("after_seen", res.get("raw_items", 0))
    removed_by_seen = res.get("removed_by_seen", 0)
    high_signal = res.get("high_signal", len([e for e in res.get("events", []) if e.tier in ("weekly", "important", "critical")]))
    empty_reason = res.get("empty_reason", "")
    reason_tail = f" empty_reason={empty_reason}" if empty_reason else ""
    cached = res.get("cached_events_added", 0)
    print(f"[{label}] sources={res['sources_checked']} failed={res['sources_failed']} collected={collected} "
          f"after_window={after_window} removed_by_window={removed_by_window} after_seen={after_seen} removed_by_seen={removed_by_seen} "
          f"dup={res['duplicates_removed']} noise={res['noise_removed']} candidates={res['candidate_events']} cached={cached} high_signal={high_signal} "
          f"ai_calls={res['ai_calls']} ai_cost=${s['cost_this_run']:.4f} monthly=${s['monthly_cost']:.2f} "
          f"critical={len(res['critical_events'])}{reason_tail}{tail}")

async def run_radar(
    radar: str,
    settings,
    state: StateStore,
    client,
    guard,
    http,
    do_ai: bool,
    weekly: bool = True,
    record_seen: bool = True,
) -> dict:
    # Weekly reports cover the whole lookback window. Frequent scans have their
    # own seen cursor, while delivery idempotency protects weekly re-runs.
    seen = set() if weekly else state.load_seen()
    if radar == "industry":
        from radars.industry import run_industry_scan
        res = await run_industry_scan(http, settings, guard, client, do_ai=do_ai, seen=seen, weekly=weekly)
    else:
        from radars.competitor import run_competitor_scan
        res = await run_competitor_scan(http, settings, guard, client, do_ai=do_ai, state=state, seen=seen, weekly=weekly)
    if weekly and hasattr(state, "load_candidates"):
        runtime = settings.get("runtime") or {}
        lookback = int((runtime.get("pipeline") or {}).get("weekly_lookback_days") or 7)
        cached = state.load_candidates(radar, lookback)
        live_events = res.get("events", [])
        live_ids = {event.event_id for event in live_events}
        additions = [event for event in cached if event.event_id not in live_ids]
        if additions:
            res["events"] = live_events + additions
            res["candidate_events"] = len(res["events"])
            res["high_signal"] = sum(event.tier in ("weekly", "important", "critical") for event in res["events"])
            if res["high_signal"]:
                res["empty_reason"] = None
        res["cached_events_added"] = len(additions)
    if record_seen and not weekly:
        if hasattr(state, "record_candidates"):
            state.record_candidates(radar, res.get("events", []))
        # Keep unalerted critical events eligible for the next scan if their
        # delivery is disabled or fails. Alerted critical events may be seen.
        pending_critical = {
            e.event_id for e in res.get("critical_events", []) if critical_is_new(state, e.event_id)
        }
        state.add_seen([eid for eid in res.get("processed_ids", []) if eid not in pending_critical])
    return res

async def deliver_weekly(radar: str, res: dict, settings, state, client, guard, no_ai, output, push, force, dry_run):
    report = build_report(radar, res, settings, client, guard, no_ai)
    # Persist the complete report before any external delivery. The weekly
    # workflow can request only Lark, but its artifact still needs both files.
    targets = OutputRouter.parse(output, settings["runtime"]["delivery"]["default_outputs"])
    ctx = DeliveryContext(
        radar=radar, report_id=report.id, title=report.title,
        dry_run=(dry_run or not push), force=force, state=state,
    )
    file_results = OutputRouter(["file"], state=state, settings=settings["runtime"]).deliver(report, ctx)
    if not file_results or not file_results[0].success:
        raise RuntimeError(f"[{radar}] weekly report file delivery failed; external delivery skipped")
    external_targets = [target for target in targets if target != "file"]
    results = file_results + OutputRouter(
        external_targets, state=state, settings=settings["runtime"]
    ).deliver(report, ctx)
    # Print PREVIEW notice for external targets when not pushing
    if not push and not dry_run:
        print(f"[{radar}] PREVIEW: payload built but NOT sent (use --push to deliver). Targets={targets}")
    return report, results

async def handle_critical(state, res, radar, can_push, force, dry_run):
    critical = res.get("critical_events", [])
    if not critical:
        return
    # Each event gets its own card and idempotency key; do not hide the fourth
    # event behind the Lark brief's three-item display cap.
    new = list({e.event_id: e for e in critical if critical_is_new(state, e.event_id)}.values())
    if not new:
        print(f"[{radar}] No new critical alerts (deduped).")
        return
    for e in new:
        print(f"[CRITICAL] {e.title} {public_source_url(e.source_url) or '来源链接不可用'}")
    if not can_push:
        print(f"[{radar}] Critical push disabled (need --push and push.critical_enabled). Not delivered.")
        return
    failed = 0
    for e in new:
        alert_id = hashlib.sha256(json.dumps(["critical", radar, e.event_id]).encode()).hexdigest()[:16]
        report = Report(
            radar=radar, period=period(), kind="critical", id=alert_id,
            events=[e], title=f"Critical Alert - {radar}",
            markdown=f"- {e.title} {public_source_url(e.source_url) or '来源链接不可用'}",
            meta={
                "event_ids": [e.event_id],
                "sources_checked": res.get("sources_checked", 0),
                "sources_failed": res.get("sources_failed", 0),
            },
        )
        # A prior send can be recorded without its critical marker if a state
        # write fails; retry the pending event rather than accepting a skip.
        was_delivered = state is not None and state.already_delivered("lark", alert_id)
        ctx = DeliveryContext(
            radar=radar, report_id=alert_id, title=report.title,
            dry_run=dry_run, force=(force or was_delivered), state=state,
        )
        results = OutputRouter(["lark"], state=state, settings={"delivery": {}}).deliver(report, ctx)
        if any(r.success and r.status == DeliveryStatus.SUCCESS.value for r in results):
            record_critical_alert(state, e.event_id)
        elif not dry_run:
            failed += 1
    if failed:
        raise RuntimeError(f"[{radar}] critical delivery failed for {failed} event(s)")

async def do_scan(radar_arg, dry_run, no_ai, output, push, force, settings, state, client):
    guard = make_guard(settings, state)
    unhealthy: list[str] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        radars = ["industry", "competitor"] if radar_arg == "all" else [radar_arg]
        for r in radars:
            # scan is ad-hoc, not weekly window
            res = await run_radar(
                r, settings, state, client, guard, http, not no_ai,
                weekly=False, record_seen=not dry_run,
            )
            print_summary(r, res, guard)
            if res.get("sources_checked", 0) > 0 and res.get("sources_failed", 0) >= res.get("sources_checked", 0):
                logger.error("[%s] HEALTH_FAIL: all configured sources failed; skipping delivery", r)
                unhealthy.append(r)
                continue
            critical_cfg = settings["runtime"].get("push", {}).get("critical_enabled", False)
            await handle_critical(state, res, r, can_push=(push and critical_cfg), force=force, dry_run=dry_run)
    if unhealthy:
        raise RuntimeError(f"all configured sources failed for: {', '.join(unhealthy)}")

async def do_weekly(radar_arg, dry_run, no_ai, output, push, force, settings, state, client):
    guard = make_guard(settings, state)
    unhealthy: list[str] = []
    delivery_failures: list[str] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        radars = ["industry", "competitor"] if radar_arg == "all" else [radar_arg]
        for r in radars:
            res = await run_radar(
                r, settings, state, client, guard, http, not no_ai,
                weekly=True, record_seen=not dry_run,
            )
            print_summary(f"{r} weekly", res, guard)
            if res.get("sources_checked", 0) > 0 and res.get("sources_failed", 0) >= res.get("sources_checked", 0):
                logger.error("[%s weekly] HEALTH_FAIL: all configured sources failed; skipping report delivery", r)
                unhealthy.append(r)
                continue
            _, results = await deliver_weekly(r, res, settings, state, client, guard, no_ai, output, push, force, dry_run)
            if push and not dry_run:
                delivery_failures.extend(f"{r}/{result.target}" for result in results
                                         if result.target != "file" and not result.success)
            critical_cfg = settings["runtime"].get("push", {}).get("critical_enabled", False)
            await handle_critical(state, res, r, can_push=(push and critical_cfg), force=force, dry_run=dry_run)
    if unhealthy or delivery_failures:
        reasons = []
        if unhealthy:
            reasons.append(f"all configured sources failed for: {', '.join(unhealthy)}")
        if delivery_failures:
            reasons.append(f"external delivery failed for: {', '.join(delivery_failures)}")
        raise RuntimeError("; ".join(reasons))

def build_smoke_report(radar: str, report_id: str | None = None) -> Report:
    if report_id:
        return Report(
            radar=radar, period=period(), kind="smoke",
            id=report_id,
            title="Delivery Test", markdown="Web3 Intelligence Radar\nDelivery Test",
            meta={"environment": os.getenv("RADAR_ENV", "test"), "status": "ok"},
        )
    return Report(
        radar=radar, period=period(), kind="smoke",
        title="Delivery Test", markdown="Web3 Intelligence Radar\nDelivery Test",
        meta={"environment": os.getenv("RADAR_ENV", "test"), "status": "ok"},
    )

async def do_output_test(target, radar, push, force, settings, state, report_id: str | None = None):
    report = build_smoke_report(radar, report_id=report_id)
    ctx = DeliveryContext(radar=radar, report_id=report.id, title=report.title,
                          dry_run=(not push), force=force, state=state)
    router = OutputRouter([target], state=state, settings=settings["runtime"])
    results = router.deliver(report, ctx)
    for r in results:
        print(r.to_log())

def sync_state_pull(state: StateStore, dry_run: bool):
    if dry_run:
        return
    # Only production namespace syncs to radar-state branch
    if getattr(state, "namespace", "production") != "production":
        logger.info(f"[state] Skip pull for namespace={state.namespace}")
        return
    git_state.pull_state(state.dir)

def sync_state_push(state: StateStore, dry_run: bool, summary: str):
    if dry_run:
        return
    if getattr(state, "namespace", "production") != "production":
        logger.info(f"[state] Skip push for namespace={state.namespace}")
        return
    git_state.push_state(state.dir, summary)

def main():
    parser = argparse.ArgumentParser(prog="radar")
    parser.add_argument("command", choices=["scan", "industry", "competitor", "resolve", "output-test", "receiver", "doctor", "ai-test"])
    parser.add_argument("--weekly", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--radar", default=None)
    parser.add_argument("--output", default=None, help="comma list: file,lark,local-http")
    parser.add_argument("--push", action="store_true", help="Actually deliver external messages (required; default off)")
    parser.add_argument("--force-push", action="store_true", help="Re-send even if already delivered")
    parser.add_argument("--target", default="lark", help="for output-test")
    parser.add_argument("--model", default="classifier", help="for ai-test: classifier|synthesis")
    parser.add_argument("--report-id", default=None, help="for output-test: override report id (acceptance smoke unique id)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    if args.command == "doctor":
        from radar.doctor import run_doctor
        raise SystemExit(run_doctor())

    if args.command == "ai-test":
        from radar.ai_test import run_ai_test
        raise SystemExit(run_ai_test(args.model))

    if args.command == "resolve":
        from collectors.resolver import resolve_all_sources
        settings = get_settings()
        state = StateStore()
        asyncio.run(resolve_all_sources(settings["sources"], None, state=state))
        print("Resolver done -> state resolved_sources.json (persisted)")
        return

    if args.command == "receiver":
        from radar.receiver import run_receiver
        run_receiver(args.host, args.port)
        return

    settings = get_settings()
    # Namespace isolation: production for scheduled, acceptance for ./scripts/acceptance.sh --e2e
    # Env RADAR_STATE_NAMESPACE overrides; default production
    ns = os.getenv("RADAR_STATE_NAMESPACE") or "production"
    state = StateStore(namespace=ns)
    client = make_client(settings)

    # State persistence: pull at start (no-op locally / in CI syncs radar-state)
    sync_state_pull(state, args.dry_run)

    radar_arg = args.radar or args.command
    if radar_arg == "scan":
        radar_arg = "all"
    if args.command in ("industry", "competitor"):
        radar_arg = args.command

    try:
        if args.command == "output-test":
            asyncio.run(do_output_test(args.target, radar_arg, args.push, args.force_push, settings, state, report_id=args.report_id))
        elif args.weekly:
            asyncio.run(do_weekly(radar_arg, args.dry_run, args.no_ai, args.output, args.push, args.force_push, settings, state, client))
        else:
            asyncio.run(do_scan(radar_arg, args.dry_run, args.no_ai, args.output, args.push, args.force_push, settings, state, client))
    finally:
        # A later radar or output can fail after an earlier delivery. Persist
        # the completed work so the next run retains cost and dedupe records.
        sync_state_push(state, args.dry_run, f"run {radar_arg}")

if __name__ == "__main__":
    main()
