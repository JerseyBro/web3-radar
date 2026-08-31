from __future__ import annotations
import asyncio
import argparse
import os
import logging
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx

from radar.config import get_settings, ROOT
from pipeline.cost_guard import CostGuard
from pipeline.llm import LLMClient
from storage.state import StateStore
from storage.store import (
    is_new_critical, mark_critical_alerted, report_path as _store_report_path,
)
from storage import git_state
from outputs.router import OutputRouter
from outputs.base import DeliveryContext
from radar.report import Report

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

def build_report(radar: str, res: dict, settings, client, guard, no_ai: bool) -> Report:
    events = res["events"]
    report_events = [e for e in events if e.tier in ("weekly", "important", "critical")]
    report_events = sorted(report_events, key=lambda x: x.score, reverse=True)[:30]
    models = settings["models"]
    synth_cfg = models.get("synthesis", {})
    synth_model = synth_cfg.get("primary")
    markdown = None
    if not no_ai and synth_model and client.available():
        prompt_path = ROOT / "prompts" / f"{radar}.md"
        markdown = synthesize_report(radar, report_events, client, guard, models, prompt_path)
    if not markdown:
        markdown = build_fallback_report(radar, report_events)
    return Report(
        radar=radar, period=period(), kind="weekly", events=report_events,
        markdown=markdown,
        meta={"ai_cost_usd": round(guard.cost_this_run, 4), "run_id": os.getenv("GITHUB_RUN_ID", "local")},
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
        lines.append(f"  - Source: {e.source_url}")
    return "\n".join(lines)

def print_summary(label: str, res: dict, guard: CostGuard):
    s = guard.summary()
    warn = guard.warning()
    tail = f" | WARN: {warn}" if warn else ""
    print(f"[{label}] sources={res['sources_checked']} failed={res['sources_failed']} raw={res['raw_items']} "
          f"dup={res['duplicates_removed']} noise={res['noise_removed']} candidates={res['candidate_events']} "
          f"ai_calls={res['ai_calls']} ai_cost=${s['cost_this_run']:.4f} monthly=${s['monthly_cost']:.2f} "
          f"critical={len(res['critical_events'])}{tail}")

async def run_radar(radar: str, settings, state: StateStore, client, guard, http, do_ai: bool) -> dict:
    seen = state.load_seen()
    if radar == "industry":
        from radars.industry import run_industry_scan
        res = await run_industry_scan(http, settings, guard, client, do_ai=do_ai, seen=seen)
    else:
        from radars.competitor import run_competitor_scan
        res = await run_competitor_scan(http, settings, guard, client, do_ai=do_ai, state=state, seen=seen)
    state.add_seen(res.get("processed_ids", []))
    return res

async def deliver_weekly(radar: str, res: dict, settings, state, client, guard, no_ai, output, push, force, dry_run):
    report = build_report(radar, res, settings, client, guard, no_ai)
    # File output always; external targets only when --push (else preview)
    targets = OutputRouter.parse(output, settings["runtime"]["delivery"]["default_outputs"])
    ctx = DeliveryContext(
        radar=radar, report_id=report.id, title=report.title,
        dry_run=(dry_run or not push), force=force, state=state,
    )
    router = OutputRouter(targets, state=state, settings=settings["runtime"])
    results = router.deliver(report, ctx)
    # Print PREVIEW notice for external targets when not pushing
    if not push and not dry_run:
        print(f"[{radar}] PREVIEW: payload built but NOT sent (use --push to deliver). Targets={targets}")
    return report, results

async def handle_critical(state, res, radar, can_push, force, dry_run):
    critical = res.get("critical_events", [])
    if not critical:
        return
    new = [e for e in critical if is_new_critical(e.event_id)]
    if not new:
        print(f"[{radar}] No new critical alerts (deduped).")
        return
    for e in new:
        print(f"[CRITICAL] {e.title} {e.source_url}")
    if not can_push:
        print(f"[{radar}] Critical push disabled (need --push and push.critical_enabled). Not delivered.")
        return
    report = Report(radar=radar, period=period(), kind="critical",
                    events=new, title=f"Critical Alert - {radar}",
                    markdown="\n".join([f"- {e.title} {e.source_url}" for e in new]),
                    meta={"event_ids": [e.event_id for e in new]})
    ctx = DeliveryContext(radar=radar, report_id=report.id, title=report.title,
                          dry_run=dry_run, force=force, state=state)
    router = OutputRouter(["lark"], state=state, settings={"delivery": {}})
    results = router.deliver(report, ctx)
    # Mark alerted only when actually delivered (success) so it can retry later if failed
    for r in results:
        if r.success and r.status != "skipped":
            for e in new:
                mark_critical_alerted(e.event_id)
                if state is not None:
                    state.record_delivery("lark", e.event_id, "ok")
            break

async def do_scan(radar_arg, dry_run, no_ai, output, push, force, settings, state, client):
    guard = make_guard(settings, state)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        radars = ["industry", "competitor"] if radar_arg == "all" else [radar_arg]
        for r in radars:
            res = await run_radar(r, settings, state, client, guard, http, not no_ai)
            print_summary(r, res, guard)
            critical_cfg = settings["runtime"].get("push", {}).get("critical_enabled", False)
            await handle_critical(state, res, r, can_push=(push and critical_cfg), force=force, dry_run=dry_run)

async def do_weekly(radar_arg, dry_run, no_ai, output, push, force, settings, state, client):
    guard = make_guard(settings, state)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        radars = ["industry", "competitor"] if radar_arg == "all" else [radar_arg]
        for r in radars:
            res = await run_radar(r, settings, state, client, guard, http, not no_ai)
            print_summary(f"{r} weekly", res, guard)
            await deliver_weekly(r, res, settings, state, client, guard, no_ai, output, push, force, dry_run)
            critical_cfg = settings["runtime"].get("push", {}).get("critical_enabled", False)
            await handle_critical(state, res, r, can_push=(push and critical_cfg), force=force, dry_run=dry_run)

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
    git_state.pull_state(state.dir)

def sync_state_push(state: StateStore, dry_run: bool, summary: str):
    if dry_run:
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
    state = StateStore()
    client = make_client(settings)

    # State persistence: pull at start (no-op locally / in CI syncs radar-state)
    sync_state_pull(state, args.dry_run)

    radar_arg = args.radar or args.command
    if radar_arg == "scan":
        radar_arg = "all"
    if args.command in ("industry", "competitor"):
        radar_arg = args.command

    if args.command == "output-test":
        asyncio.run(do_output_test(args.target, radar_arg, args.push, args.force_push, settings, state, report_id=args.report_id))
        return

    if args.weekly:
        asyncio.run(do_weekly(radar_arg, args.dry_run, args.no_ai, args.output, args.push, args.force_push, settings, state, client))
    else:
        asyncio.run(do_scan(radar_arg, args.dry_run, args.no_ai, args.output, args.push, args.force_push, settings, state, client))

    # Persist state back to radar-state branch (cost/seen/deliveries)
    sync_state_push(state, args.dry_run, f"run {radar_arg}")

if __name__ == "__main__":
    main()
