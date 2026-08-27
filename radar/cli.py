from __future__ import annotations
import asyncio
import argparse
import os
import logging
import json
from pathlib import Path
from datetime import datetime, timezone
import httpx

from radar.config import get_settings
from pipeline.cost_guard import CostGuard
from pipeline.openai_client import OpenAIClient
from storage.store import load_critical_alerts, save_critical_alerts, report_path, is_new_critical, mark_critical_alerted
from outputs.lark import build_industry_card, build_competitor_card, send_lark
from pipeline.analyze import synthesize_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parent.parent

def make_guard(settings):
    models = settings["models"]
    pricing = models.get("pricing",{})
    return CostGuard(
        budget_usd=float(models.get("monthly_ai_budget_usd",5)),
        max_calls_per_run=int(models.get("max_ai_calls_per_run",20)),
        state_path=ROOT / "storage" / "state" / "ai_cost.json",
        pricing=pricing,
    )

def make_client(settings):
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    return OpenAIClient(api_key=api_key, base_url=base_url)

async def do_scan(radar: str, dry_run: bool, no_ai: bool):
    settings = get_settings()
    guard = make_guard(settings)
    client_ai = make_client(settings)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        if radar in ("industry","all"):
            from radars.industry import run_industry_scan
            res = await run_industry_scan(http, settings, guard, client_ai, do_ai=not no_ai)
            print_summary("industry", res, guard)
            await handle_critical(res, "industry", dry_run)
        if radar in ("competitor","all"):
            from radars.competitor import run_competitor_scan
            res = await run_competitor_scan(http, settings, guard, client_ai, do_ai=not no_ai)
            print_summary("competitor", res, guard)
            await handle_critical(res, "competitor", dry_run)

async def do_weekly(radar: str, dry_run: bool, no_ai: bool):
    settings = get_settings()
    guard = make_guard(settings)
    client_ai = make_client(settings)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        radars = []
        if radar == "all": radars = ["industry","competitor"]
        else: radars = [radar]
        for r in radars:
            if r == "industry":
                from radars.industry import run_industry_scan
                res = await run_industry_scan(http, settings, guard, client_ai, do_ai=not no_ai)
            else:
                from radars.competitor import run_competitor_scan
                res = await run_competitor_scan(http, settings, guard, client_ai, do_ai=not no_ai)
            print_summary(f"{r} weekly", res, guard)
            # synthesize report
            events = res["events"]
            # Only weekly+ important+ critical go into report
            report_events = [e for e in events if e.tier in ("weekly","important","critical")]
            report_events = sorted(report_events, key=lambda x: x.score, reverse=True)[:30]
            models = settings["models"]
            synth_model = models.get("synthesis_model","gpt-4o-mini")
            if "5.6" in synth_model:
                synth_model = "gpt-4o-mini"
            report_md = None
            if not no_ai and report_events:
                prompt_path = ROOT / "prompts" / f"{r}.md"
                # Use guard check
                report_md = synthesize_report(r, report_events, client_ai, guard, synth_model, prompt_path)
            if not report_md:
                # fallback deterministic report
                report_md = build_fallback_report(r, report_events)
            # Save report
            p = report_path(r)
            p.parent.mkdir(parents=True, exist_ok=True)
            if not dry_run:
                p.write_text(report_md, encoding="utf-8")
                print(f"Report saved: {p}")
            else:
                print(f"[DRY-RUN] Report would be saved: {p}\n---\n{report_md[:1500]}")
            # Lark push for weekly (always push weekly, not just critical)
            await push_weekly_lark(r, report_events, report_md, dry_run)
            await handle_critical(res, r, dry_run)

def build_fallback_report(radar: str, events: list) -> str:
    lines = [f"# {radar.capitalize()} Weekly Report - {datetime.now(timezone.utc).strftime('%Y-W%V')}", ""]
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
    print(f"[{label}] sources_checked={res['sources_checked']} failed={res['sources_failed']} raw={res['raw_items']} dup_removed={res['duplicates_removed']} noise_removed={res['noise_removed']} candidates={res['candidate_events']} ai_calls={res['ai_calls']} ai_cost=${s['cost_this_run']:.4f} critical={len(res['critical_events'])}")

async def handle_critical(res: dict, radar: str, dry_run: bool):
    critical = res.get("critical_events",[])
    if not critical:
        return
    new = []
    for e in critical:
        # Dedup: never re-alert same event_id
        if not is_new_critical(e.event_id):
            continue
        new.append(e)
    if not new:
        print(f"[{radar}] No new critical alerts (deduped)")
        return
    for e in new:
        print(f"[CRITICAL] {e.title} {e.source_url}")
    webhook = os.getenv(f"LARK_WEBHOOK_{radar.upper()}")
    secret = os.getenv(f"LARK_SIGNING_SECRET_{radar.upper()}")
    if webhook:
        payload = build_industry_card(f"Critical Alert - {radar}", "\n".join([f"{e.title} - {e.source_url}" for e in new[:3]]), [{"title":e.title,"url":e.source_url,"score":e.score} for e in new])
        send_lark(webhook, payload, secret, dry_run=dry_run)
    if not dry_run:
        for e in new:
            mark_critical_alerted(e.event_id)

async def push_weekly_lark(radar: str, events: list, report_md: str, dry_run: bool):
    webhook = os.getenv(f"LARK_WEBHOOK_{radar.upper()}")
    secret = os.getenv(f"LARK_SIGNING_SECRET_{radar.upper()}")
    if not webhook:
        print(f"[{radar}] No webhook, skip Lark push")
        return
    summary = report_md[:600]
    ev_dicts = [{"title":e.title,"url":e.source_url,"score":e.score} for e in events[:6]]
    if radar == "industry":
        payload = build_industry_card(f"Weekly {radar}", summary, ev_dicts)
    else:
        payload = build_competitor_card(f"Weekly {radar}", summary, ev_dicts)
    res = send_lark(webhook, payload, secret, dry_run=dry_run)
    print(f"[{radar}] Lark push: {res}")

def main():
    parser = argparse.ArgumentParser(prog="radar")
    parser.add_argument("command", choices=["scan","industry","competitor","resolve"])
    parser.add_argument("--weekly", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--radar", default=None)
    args = parser.parse_args()

    if args.command == "resolve":
        from collectors.resolver import resolve_all_sources
        from pathlib import Path
        settings = get_settings()
        asyncio.run(resolve_all_sources(settings["sources"], ROOT / "storage" / "state" / "resolved_sources.json"))
        print("Resolver done -> storage/state/resolved_sources.json")
        return

    radar = args.radar or args.command
    if radar == "scan":
        radar = "all"
    if args.command in ("industry","competitor"):
        radar = args.command

    if args.weekly:
        asyncio.run(do_weekly(radar, dry_run=args.dry_run, no_ai=args.no_ai))
    else:
        asyncio.run(do_scan(radar, dry_run=args.dry_run, no_ai=args.no_ai))

if __name__ == "__main__":
    main()
