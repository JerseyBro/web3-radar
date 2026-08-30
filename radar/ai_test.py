from __future__ import annotations
import json
import tempfile
import time
from pathlib import Path

from radar.config import get_settings
from pipeline.llm import LLMClient
from pipeline.llm.registry import resolve_role
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


def _role_label(role: str, models: dict) -> str:
    resolved = resolve_role(models, role)
    pm = resolved.get("primary")
    if pm:
        return f"{pm[0]}/{pm[1]}"
    return "?"


def run_ai_test(model_kind: str = "classifier") -> int:
    settings = get_settings()
    models = settings["models"]
    role = model_kind if model_kind in ("classifier", "synthesis") else "classifier"
    role_label = _role_label(role, models)

    if role == "synthesis":
        system, user = _synthesis_prompt()
    else:
        system, user = _classifier_prompt()

    client = LLMClient(models)

    print("AI Smoke Test\n")
    print(f"Role: {role}")
    print(f"Resolved: {role_label}\n")

    if not client.available():
        print("LLM provider: BLOCKED_BY_CONFIGURATION (no API key / SDK)")
        print("Result: BLOCKED_BY_CONFIGURATION")
        return 0

    guard = CostGuard(
        state=StateStore(state_dir=Path(tempfile.mkdtemp())),
        budget_usd=float(models.get("monthly_ai_budget_usd", 5)),
        max_calls_per_run=int(models.get("max_ai_calls_per_run", 20)),
        pricing=models.get("pricing", {}),
    )

    # Check generation via role-based API (provider-agnostic)
    t0 = time.monotonic()
    parsed, usage = client.generate(role, system, user, schema={"type": "object"}, radar=role)
    latency = time.monotonic() - t0

    provider = usage.get("provider", "?")
    model = usage.get("model", "?")
    print(f"Provider: {provider}")
    print(f"Model: {model}")
    print(f"Latency: {latency:.2f}s")

    if usage.get("cost_unknown"):
        print("Cost: COST_UNKNOWN (pricing not configured)")
    if usage.get("usage_unavailable"):
        print("Usage: USAGE_UNKNOWN (provider did not return token counts)")

    if not client.available():
        print("API: BLOCKED_BY_CONFIGURATION")
        print("Result: BLOCKED_BY_CONFIGURATION")
        return 0

    if parsed is None:
        print("Structured Output: FAIL")
        err = usage.get("error", "unknown")
        print(f"Error: {err}")
        print("Result: FAIL")
        return 1

    print("Structured Output: PASS")

    if role == "synthesis":
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

    in_tok = usage.get("input_tokens", 0) or 0
    out_tok = usage.get("output_tokens", 0) or 0
    # Record via CostGuard (handles COST_UNKNOWN / USAGE_UNKNOWN)
    guard.record(
        model, in_tok, out_tok, role,
        provider=provider,
        cost_unknown=usage.get("cost_unknown", False),
        usage_unavailable=usage.get("usage_unavailable", False),
    )
    cost = guard.summary()["cost_this_run"]

    print(f"Input Tokens: {in_tok}")
    print(f"Output Tokens: {out_tok}")
    print(f"Estimated Cost: ${cost:.6f}")
    print("Result: PASS")
    return 0
