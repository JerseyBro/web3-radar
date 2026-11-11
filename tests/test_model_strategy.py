"""Provider and solo-builder scoring regressions; no network or API keys."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from radar.config import get_settings
from radar.schema import Event, EventType, RadarType
from pipeline.analyze import analyze_events, synthesize_report
from pipeline.cost_guard import CostGuard
from pipeline.llm.openai_compatible import OpenAICompatibleProvider
from pipeline.llm.registry import resolve_role
from pipeline.score import apply_score, score_industry
from storage.state import StateStore


def _event() -> Event:
    return Event(event_id="builder-1", radar=RadarType.industry, source="official",
                 source_url="https://example.org/release", title="New developer API",
                 excerpt="A new SDK endpoint was announced.")


def _guard(models: dict, state_dir: Path) -> CostGuard:
    return CostGuard(state=StateStore(state_dir=state_dir, namespace="test"),
                     budget_usd=5, pricing=models.get("pricing", {}))


def test_default_models_have_current_pricing():
    models = get_settings()["models"]
    assert resolve_role(models, "classifier")["primary"] == ("deepseek", "deepseek-flash")
    assert resolve_role(models, "synthesis")["fallback"] is None
    assert models["pricing"]["gpt-6-luna"] == {"input": 0.10, "output": 0.50}
    for role in ("classifier", "synthesis"):
        for slot in resolve_role(models, role).values():
            if slot:
                assert models["pricing"][slot[1]]["input"] > 0
                assert models["pricing"][slot[1]]["output"] > 0


def test_deepseek_disables_default_thinking_for_json():
    provider = OpenAICompatibleProvider(provider_name="deepseek", api_key=None)
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"events": []}'))], usage=None)
    parsed, _ = provider.call_json("deepseek-flash", "Return JSON", "events", schema={"type": "object"})
    assert parsed == {"events": []}
    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert kwargs["response_format"] == {"type": "json_object"}


def test_optional_openai_luna_disables_reasoning_for_json():
    provider = OpenAICompatibleProvider(provider_name="openai", api_key=None)
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"events": []}'))], usage=None)
    parsed, _ = provider.call_json("gpt-6-luna", "Return JSON", "events", schema={"type": "object"})
    assert parsed == {"events": []}
    assert provider._client.chat.completions.create.call_args.kwargs["reasoning_effort"] == "none"


def test_builder_relevance_is_scored_independently_of_wallet_relevance():
    event = _event()
    event.builder_relevance = 95
    event.wallet_relevance = 0
    score = score_industry(event, get_settings()["scoring"]["industry"]["weights"])
    assert score >= 60


def test_snapshot_and_maintenance_commit_do_not_become_high_signal_by_score_alone():
    metric = _event()
    metric.event_type = EventType.defi_metric
    metric.title = "TVL Chain: $0"
    metric.impact = 100
    metric.builder_relevance = 100
    maintenance = _event()
    maintenance.event_id = "builder-2"
    maintenance.event_type = EventType.docs_update
    maintenance.title = "ethereum/EIPs: CI: Pin build runner"
    maintenance.impact = 100
    maintenance.builder_relevance = 100
    apply_score([metric, maintenance], "industry", get_settings()["scoring"])
    assert metric.tier == "archive"
    assert maintenance.tier == "noise"


def test_classifier_validates_free_text_and_tags():
    models = {"roles": {"classifier": {"primary": {"provider": "deepseek", "model": "priced"}, "fallback": None}},
              "pricing": {"priced": {"input": 1, "output": 1}}}
    client = MagicMock()
    client.available.return_value = True
    client.generate.return_value = ({"events": [{"event_id": "builder-1", "builder_relevance": 105,
                                                 "tags": "bad", "developer_action": "Verify SDK behavior"}]},
                                    {"model": "priced", "input_tokens": 10, "output_tokens": 10})
    with TemporaryDirectory() as tmp:
        event = _event()
        analyze_events([event], "industry", client, _guard(models, Path(tmp)), models)
    assert event.builder_relevance == 100
    assert event.tags == []
    assert event.developer_action == "Verify SDK behavior"


def test_unpriced_model_skips_live_ai():
    models = {"roles": {"classifier": {"primary": {"provider": "deepseek", "model": "unpriced"}, "fallback": None}},
              "pricing": {}}
    client = MagicMock()
    client.available.return_value = True
    with TemporaryDirectory() as tmp:
        event = _event()
        analyze_events([event], "industry", client, _guard(models, Path(tmp)), models)
    client.generate.assert_not_called()


def test_synthesis_requires_source_link_in_json_report():
    models = {"roles": {"synthesis": {"primary": {"provider": "deepseek", "model": "priced"}, "fallback": None}},
              "pricing": {"priced": {"input": 1, "output": 1}}}
    client = MagicMock()
    client.available.return_value = True
    client.generate.return_value = ({"report": "# Unlinked claim"},
                                    {"model": "priced", "input_tokens": 10, "output_tokens": 10})
    with TemporaryDirectory() as tmp:
        report = synthesize_report("industry", [_event()], client, _guard(models, Path(tmp)), models,
                                   Path(tmp) / "missing-prompt.md")
    assert report is None
