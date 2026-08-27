from __future__ import annotations
import os
import json
import tempfile
from pathlib import Path

from radar.config import get_settings, ROOT
from pipeline.openai_client import OpenAIClient
from pipeline.cost_guard import CostGuard
from storage.state import StateStore


FIXTURE = {
    "event_id": "ai-test-1",
    "title": "Example wallet adds a new chain and cross-chain swap support",
    "excerpt": "The wallet now supports an additional L1 and native cross-chain swap routing.",
    "source": "test",
    "source_url": "https://example.com/announcement",
    "entity": "Example Wallet",
}


def _classifier_prompt():
    system = "You are a Web3 intelligence classifier. Return JSON only."
    schema_hint = (
        'Return JSON: {"events":[{"event_id":"ai-test-1",'
        '"event_type":"wallet_feature","wallet_relevance":0-100,'
        '"impact":0-100,"credibility":0-100,"ai_summary":"..."}]}'
    )
    user = json.dumps([FIXTURE], ensure_ascii=False) + "\n\n" + schema_hint
    return system, user


def _synthesis_prompt():
    system = "You are a Web3 intelligence report writer. Return a short Markdown summary."
    user = "Summarize in 3 bullet points: a wallet added a new chain and cross-chain swap support."
    return system, user


def run_ai_test(model_kind: str = "classifier") -> int:
    settings = get_settings()
    models = settings["models"]
    if model_kind == "synthesis":
        primary = models.get("synthesis", {}).get("primary")
        system, user = _synthesis_prompt()
    else:
        primary = models.get("classifier", {}).get("primary")
        system, user = _classifier_prompt()

    client = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"), base_url=os.getenv("OPENAI_BASE_URL"))

    print("AI Smoke Test\n")
    print(f"Model: {primary}\n")

    if not client.available():
        print("OPENAI_API_KEY / openai package: BLOCKED_BY_CONFIGURATION")
        print("Result: BLOCKED_BY_CONFIGURATION")
        return 0

    guard = CostGuard(state=StateStore(state_dir=Path(tempfile.mkdtemp())),
                      budget_usd=float(models.get("monthly_ai_budget_usd", 5)),
                      max_calls_per_run=int(models.get("max_ai_calls_per_run", 20)),
                      pricing=models.get("pricing", {}))

    print("API: PASS")
    parsed, usage = client.call_json(primary, system, user, schema={"type": "object"}, radar=model_kind)
    in_tok = usage.get("input_tokens", 0) or 0
    out_tok = usage.get("output_tokens", 0) or 0
    guard.record(primary, in_tok, out_tok, model_kind)
    cost = guard.summary()["cost_this_run"]

    if parsed is None:
        print("Structured Output: FAIL")
        print("Result: FAIL")
        return 1
    print("Structured Output: PASS")

    if model_kind == "synthesis":
        ok = isinstance(parsed, dict) or isinstance(parsed, str)
        print(f"Content length: {len(json.dumps(parsed))}")
    else:
        events = parsed.get("events", []) if isinstance(parsed, dict) else []
        ev = next((e for e in events if e.get("event_id") == "ai-test-1"), None)
        if ev:
            print(f"Event Type: {ev.get('event_type')}")
            print(f"Wallet Relevance: {ev.get('wallet_relevance')}")
        else:
            print("Event Type: (none)")
            print("Result: FAIL")
            return 1

    print(f"Input Tokens: {in_tok}")
    print(f"Output Tokens: {out_tok}")
    print(f"Estimated Cost: ${cost:.6f}")
    print("Result: PASS")
    return 0
