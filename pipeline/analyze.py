from __future__ import annotations
import json
import logging
from pathlib import Path
from radar.schema import Event
from pipeline.cost_guard import CostGuard

# LLMClient is provider-agnostic; pipeline never branches on provider name.
try:
    from pipeline.llm import LLMClient
except ImportError:
    from pipeline.llm.client import LLMClient  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

CLASSIFIER_SCHEMA_HINT = """Return JSON with:
{
  "events": [
    {
      "event_id": "...",
      "credibility": 0-100,
      "novelty": 0-100,
      "impact": 0-100,
      "wallet_relevance": 0-100,
      "technical_significance": 0-100,
      "money_flow_significance": 0-100,
      "strategic_importance": 0-100,
      "execution_signal": 0-100,
      "tags": ["tag1"],
      "ai_summary": "1-2 sentence summary",
      "why_it_matters": "1 sentence",
      "wallet_implication": "1 sentence or null"
    }
  ]
}"""


def build_classifier_prompt(events: list[Event], radar: str) -> tuple[str, str]:
    system = f"You are a Web3 intelligence classifier for {radar} radar. Rate each event 0-100 on all dimensions. Be strict. Return JSON only."
    items = []
    for e in events:
        items.append({
            "event_id": e.event_id,
            "title": e.title,
            "excerpt": e.excerpt[:400],
            "source": e.source,
            "source_url": e.source_url,
            "entity": e.entity,
        })
    user = f"Events to classify ({radar}):\n{json.dumps(items, ensure_ascii=False, indent=2)}\n\n{CLASSIFIER_SCHEMA_HINT}"
    return system, user


def analyze_events(events: list[Event], radar: str, client, guard: CostGuard, models: dict, batch_size: int = 10) -> list[Event]:
    """Classify events via LLM. Accepts LLMClient or legacy OpenAIClient."""
    if not events:
        return events
    if not client.available():
        logger.info("Classifier AI disabled (no LLM provider available). Keeping deterministic scoring.")
        return events

    # Resolve role via registry so we get the model name for cost estimation.
    # LLMClient.generate handles provider+model routing and cross-provider fallback.
    from pipeline.llm.registry import resolve_role

    role_cfg = resolve_role(models, "classifier")
    primary = role_cfg.get("primary")
    if primary is None:
        logger.info("Classifier AI disabled (no primary model configured). Keeping deterministic scoring.")
        return events

    scored = []
    for i in range(0, len(events), batch_size):
        batch = events[i:i + batch_size]
        system, user = build_classifier_prompt(batch, radar)
        # Estimate cost using the resolved model name (provider-agnostic pricing lookup handles unknown models).
        _, model_name = primary
        est_cost = guard.estimate_cost(model_name, len(system + user) // 4, 800)
        ok, reason = guard.can_call(est_cost)
        if not ok:
            logger.warning(f"CostGuard blocked AI call: {reason}")
            break
        # Unified path: role-based generate with cross-provider fallback.
        # Legacy OpenAIClient also works (has call_json but not generate) — detect and adapt.
        if hasattr(client, "generate"):
            parsed, usage = client.generate("classifier", system, user, schema={"type": "object"}, radar=radar)
        else:
            # Legacy shim path
            _, model_name = primary
            parsed, usage = client.call_json(model_name, system, user, schema={"type": "object"}, radar=radar)

        # Guard handles COST_UNKNOWN / USAGE_UNKNOWN gracefully.
        guard.record(
            usage.get("model") or model_name,
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            radar,
            provider=usage.get("provider"),
            cost_unknown=usage.get("cost_unknown", False),
            usage_unavailable=usage.get("usage_unavailable", False),
        )
        if not parsed or "events" not in parsed:
            logger.warning(f"AI classifier returned no data for batch {i}")
            continue
        by_id = {x.event_id: x for x in batch}
        for item in parsed["events"]:
            eid = item.get("event_id")
            if eid not in by_id:
                continue
            ev = by_id[eid]
            for k in ["credibility", "novelty", "impact", "wallet_relevance", "technical_significance", "money_flow_significance", "strategic_importance", "execution_signal"]:
                if k in item:
                    try:
                        setattr(ev, k, max(0, min(100, int(item[k]))))
                    except:  # noqa: E722
                        pass
            ev.tags = item.get("tags", ev.tags)[:10]
            ev.ai_summary = item.get("ai_summary")
            ev.why_it_matters = item.get("why_it_matters")
            ev.wallet_implication = item.get("wallet_implication")
        scored.extend(batch)
    return events


def synthesize_report(radar: str, events: list[Event], client, guard: CostGuard, models: dict, prompt_path: Path) -> str | None:
    if not client.available():
        return None

    from pipeline.llm.registry import resolve_role

    role_cfg = resolve_role(models, "synthesis")
    primary = role_cfg.get("primary")
    if primary is None:
        return None

    prompt_template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "Summarize events."
    top = sorted(events, key=lambda x: x.score, reverse=True)[:20]
    payload = [{"title": e.title, "score": e.score, "source": e.source, "url": e.source_url, "summary": e.ai_summary or e.excerpt[:300], "why": e.why_it_matters, "wallet": e.wallet_implication} for e in top]
    system = "You are a Web3 intelligence report writer. Use the template structure exactly. Be concise, high-signal. Keep Source URLs."
    user = f"Template:\n{prompt_template}\n\nEvents (ranked):\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n\nGenerate the weekly report in Markdown following the template sections."

    _, model_name = primary
    est_cost = guard.estimate_cost(model_name, len(system + user) // 4, 2000)
    ok, reason = guard.can_call(est_cost)
    if not ok:
        logger.warning(f"CostGuard blocked synthesis: {reason}")
        return None

    if hasattr(client, "generate"):
        parsed, usage = client.generate("synthesis", system, user, radar=radar)
    else:
        parsed, usage = client.call_json(model_name, system, user, radar=radar)

    guard.record(
        usage.get("model") or model_name,
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
        radar,
        provider=usage.get("provider"),
        cost_unknown=usage.get("cost_unknown", False),
        usage_unavailable=usage.get("usage_unavailable", False),
    )

    if parsed is None:
        return None
    if isinstance(parsed, dict) and "report" in parsed:
        return parsed["report"]
    if isinstance(parsed, dict) and "content" in parsed:
        return parsed["content"]
    return json.dumps(parsed, ensure_ascii=False, indent=2)
