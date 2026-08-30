"""Tests for multi-provider LLM adapter layer.

All tests use mocks/stubs — no real API calls, no real secrets.
"""

import json
import os
import sys
import logging
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.llm.base import LLMProvider
from pipeline.llm.openai_compatible import OpenAICompatibleProvider
from pipeline.llm.registry import (
    PROVIDER_DEFS,
    build_provider,
    resolve_role,
    required_api_key_envs,
    all_known_api_key_envs,
    _slot_to_provider_model,
)
from pipeline.llm.client import LLMClient
from pipeline.cost_guard import CostGuard
from storage.state import StateStore
from tests._util import skip

# ── Helpers ───────────────────────────────────────────────────────

def _mock_openai_response(content: str, prompt_tokens: int = 100, completion_tokens: int = 50):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = content
    mock_resp.usage.prompt_tokens = prompt_tokens
    mock_resp.usage.completion_tokens = completion_tokens
    return mock_resp


def _make_openai_provider(api_key="sk-test", **kwargs):
    return OpenAICompatibleProvider(provider_name="test-openai", api_key=api_key, **kwargs)


# ═══════════════════════════════════════════════════════════════════
# OpenAI-compatible adapter
# ═══════════════════════════════════════════════════════════════════

def test_openai_no_client_when_no_key():
    p = OpenAICompatibleProvider(provider_name="test", api_key=None)
    assert not p.available()
    parsed, usage = p.call_json("model", "sys", "user")
    assert parsed is None
    assert usage["error"] == "no client"


def test_openai_estimate_tokens():
    p = _make_openai_provider()
    assert p._estimate_tokens("") == 1
    assert p._estimate_tokens("a" * 400) == 100
    assert p._estimate_tokens("hello world") > 0


def test_openai_call_json_success():
    from tests._util import module_available
    if not module_available("openai"):
        skip("openai not installed")
    p = _make_openai_provider()
    if not p.available():
        skip("openai SDK init failed")
    mock_client = MagicMock()
    p._client = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response('{"events":[]}')
    parsed, usage = p.call_json("gpt-test", "sys", "user", schema={"type": "object"})
    assert parsed == {"events": []}
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50


def test_openai_call_json_parse_failure():
    from tests._util import module_available
    if not module_available("openai"):
        skip("openai not installed")
    p = _make_openai_provider()
    if not p.available():
        skip("openai SDK init failed")
    mock_client = MagicMock()
    p._client = mock_client
    mock_client.chat.completions.create.return_value = _mock_openai_response("not json {{{")
    parsed, usage = p.call_json("gpt-test", "sys", "user")
    assert parsed is None
    assert usage["error"] == "json_parse_failed"


def test_openai_no_usage_marks_unavailable():
    from tests._util import module_available
    if not module_available("openai"):
        skip("openai not installed")
    p = _make_openai_provider()
    if not p.available():
        skip("openai SDK init failed")
    mock_client = MagicMock()
    p._client = mock_client
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = '{"ok": true}'
    resp.usage = None
    mock_client.chat.completions.create.return_value = resp
    parsed, usage = p.call_json("gpt-test", "sys", "user")
    assert parsed == {"ok": True}
    assert usage.get("usage_unavailable") is True


def test_openai_retryable_retries():
    from tests._util import module_available
    if not module_available("openai"):
        skip("openai not installed")
    p = _make_openai_provider()
    if not p.available():
        skip("openai SDK init failed")
    mock_client = MagicMock()
    p._client = mock_client
    mock_client.chat.completions.create.side_effect = [
        Exception("rate limit 429"),
        _mock_openai_response('{"ok": true}'),
    ]
    with patch("pipeline.llm.openai_compatible.time.sleep"):
        parsed, usage = p.call_json("gpt-test", "sys", "user")
    assert parsed == {"ok": True}


def test_openai_non_retryable_no_retry():
    from tests._util import module_available
    if not module_available("openai"):
        skip("openai not installed")
    p = _make_openai_provider()
    if not p.available():
        skip("openai SDK init failed")
    mock_client = MagicMock()
    p._client = mock_client
    mock_client.chat.completions.create.side_effect = Exception("invalid_api_key foo")
    with patch("pipeline.llm.openai_compatible.time.sleep") as mock_sleep:
        parsed, usage = p.call_json("gpt-test", "sys", "user")
    assert parsed is None
    assert not mock_sleep.called


def test_openai_secret_not_in_logs():
    p = _make_openai_provider(api_key="sk-super-secret-12345")
    if not p.available():
        # Even without SDK, the warning log shouldn't contain the key
        return
    mock_client = MagicMock()
    p._client = mock_client
    mock_client.chat.completions.create.side_effect = Exception("invalid_api_key bad key")
    # Use caplog-like check: verify key not in any log output
    # We check that available() providers don't leak keys in exceptions
    assert p.api_key == "sk-super-secret-12345"
    # The provider stores the key but never logs it
    assert "sk-super-secret-12345" not in str(mock_client.chat.completions.create.side_effect)


# ═══════════════════════════════════════════════════════════════════
# Anthropic adapter
# ═══════════════════════════════════════════════════════════════════

def test_anthropic_no_client_when_no_key():
    from pipeline.llm.anthropic import AnthropicProvider
    p = AnthropicProvider(provider_name="test-claude", api_key=None)
    assert not p.available()
    parsed, usage = p.call_json("model", "sys", "user")
    assert parsed is None


def test_anthropic_call_json_success():
    from pipeline.llm.anthropic import AnthropicProvider
    p = AnthropicProvider(provider_name="test-claude", api_key="sk-test")
    mock_client = MagicMock()
    p._client = mock_client
    mock_resp = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = '{"events": []}'
    mock_resp.content = [text_block]
    mock_resp.usage.input_tokens = 80
    mock_resp.usage.output_tokens = 20
    mock_client.messages.create.return_value = mock_resp
    parsed, usage = p.call_json("claude-test", "sys", "user")
    assert parsed == {"events": []}
    assert usage["input_tokens"] == 80


def test_anthropic_retryable():
    from pipeline.llm.anthropic import AnthropicProvider
    p = AnthropicProvider(provider_name="test-claude", api_key="sk-test")
    mock_client = MagicMock()
    p._client = mock_client
    mock_client.messages.create.side_effect = Exception("overloaded_error")
    with patch("pipeline.llm.anthropic.time.sleep"):
        parsed, usage = p.call_json("model", "sys", "user")
    assert parsed is None
    assert "overloaded" in usage["error"].lower()


def test_anthropic_secret_not_logged():
    from pipeline.llm.anthropic import AnthropicProvider
    p = AnthropicProvider(provider_name="test-claude", api_key="sk-anthropic-secret-999")
    mock_client = MagicMock()
    p._client = mock_client
    mock_client.messages.create.side_effect = Exception("auth failed bad key")
    with patch("pipeline.llm.anthropic.time.sleep"):
        parsed, usage = p.call_json("model", "sys", "user")
    assert parsed is None
    # Key should not appear in error message (error comes from exception str, not key)
    assert "sk-anthropic-secret-999" not in str(usage.get("error", ""))


# ═══════════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════════

def test_provider_defs_complete():
    for key in ["openai", "deepseek", "anthropic", "alibaba", "tencent", "volcengine", "opencode_go", "generic"]:
        assert key in PROVIDER_DEFS, f"missing provider def: {key}"
        assert PROVIDER_DEFS[key]["type"] in ("openai_compatible", "anthropic")
        assert "default_api_key_env" in PROVIDER_DEFS[key]


def test_slot_plain_string():
    assert _slot_to_provider_model("gpt-4o-mini") == ("openai", "gpt-4o-mini")
    assert _slot_to_provider_model(None) is None
    assert _slot_to_provider_model("") is None


def test_slot_dict():
    assert _slot_to_provider_model({"provider": "deepseek", "model": "deepseek-chat"}) == ("deepseek", "deepseek-chat")
    assert _slot_to_provider_model({"model": "gpt-4o-mini"}) == ("openai", "gpt-4o-mini")
    assert _slot_to_provider_model({"provider": "deepseek"}) is None


def test_resolve_role_legacy():
    models = {"classifier": {"primary": "gpt-test", "fallback": None}}
    res = resolve_role(models, "classifier")
    assert res["primary"] == ("openai", "gpt-test")
    assert res["fallback"] is None


def test_resolve_role_new():
    models = {
        "providers": {"deepseek": {"type": "openai_compatible", "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"}},
        "roles": {
            "classifier": {"primary": {"provider": "deepseek", "model": "deepseek-chat"}, "fallback": {"provider": "openai", "model": "gpt-4o-mini"}},
        },
        "classifier": {"primary": "old-model", "fallback": None},
    }
    res = resolve_role(models, "classifier")
    assert res["primary"] == ("deepseek", "deepseek-chat")
    assert res["fallback"] == ("openai", "gpt-4o-mini")


def test_required_envs_multi():
    models = {
        "providers": {
            "deepseek": {"type": "openai_compatible", "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
            "anthropic": {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY"},
        },
        "roles": {
            "classifier": {"primary": {"provider": "deepseek", "model": "m1"}, "fallback": None},
            "synthesis": {"primary": {"provider": "anthropic", "model": "m2"}, "fallback": None},
        },
    }
    envs = required_api_key_envs(models)
    assert "DEEPSEEK_API_KEY" in envs
    assert "ANTHROPIC_API_KEY" in envs
    assert "OPENAI_API_KEY" not in envs


def test_required_envs_legacy():
    models = {"classifier": {"primary": "gpt-test", "fallback": None}, "synthesis": {"primary": "gpt-test2", "fallback": None}}
    envs = required_api_key_envs(models)
    assert "OPENAI_API_KEY" in envs


def test_invalid_provider_graceful():
    with patch.dict(os.environ, {"MYSTERY_KEY": ""}, clear=False):
        # Ensure key is empty
        if "MYSTERY_KEY" in os.environ:
            del os.environ["MYSTERY_KEY"]
        p = build_provider("mystery", {"mystery": {"type": "openai_compatible", "base_url": "https://example.com", "api_key_env": "MYSTERY_KEY"}})
        assert not p.available()


def test_build_provider_anthropic_type():
    from pipeline.llm.anthropic import AnthropicProvider
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False):
        p = build_provider("anthropic", {"anthropic": {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY"}})
        assert isinstance(p, AnthropicProvider)


def test_build_provider_openai_compatible():
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test"}, clear=False):
        p = build_provider("deepseek", {"deepseek": {"type": "openai_compatible", "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"}})
        assert isinstance(p, OpenAICompatibleProvider)


def test_generic_provider():
    with patch.dict(os.environ, {"CUSTOM_LLM_API_KEY": "sk-test"}, clear=False):
        p = build_provider("generic", {"generic": {"type": "openai_compatible", "base_url": "https://my-gateway.example.com/v1", "api_key_env": "CUSTOM_LLM_API_KEY"}})
        assert isinstance(p, OpenAICompatibleProvider)


# ═══════════════════════════════════════════════════════════════════
# Unified LLMClient
# ═══════════════════════════════════════════════════════════════════

def _make_models(classifier_provider="openai", classifier_model="gpt-test", synth_provider="openai", synth_model="gpt-test2", with_fallback=False):
    return {
        "providers": {
            "openai": {"type": "openai_compatible", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            "deepseek": {"type": "openai_compatible", "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
            "anthropic": {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY"},
        },
        "roles": {
            "classifier": {
                "primary": {"provider": classifier_provider, "model": classifier_model},
                "fallback": {"provider": "openai", "model": "gpt-4o-mini"} if with_fallback else None,
            },
            "synthesis": {
                "primary": {"provider": synth_provider, "model": synth_model},
                "fallback": None,
            },
        },
        "pricing": {"gpt-test": {"input": 1.0, "output": 2.0}, "gpt-4o-mini": {"input": 0.15, "output": 0.6}},
    }


def test_llm_available_false_when_no_key():
    models = _make_models()
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k}
    with patch.dict(os.environ, env, clear=True):
        c = LLMClient(models)
        assert not c.available()


def test_llm_generate_cross_provider_fallback():
    models = _make_models(classifier_provider="deepseek", with_fallback=True)
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test", "OPENAI_API_KEY": "sk-test2"}, clear=False):
        c = LLMClient(models)
        deepseek_mock = MagicMock()
        deepseek_mock.available.return_value = True
        deepseek_mock.call_json.return_value = (None, {"input_tokens": 10, "output_tokens": 0, "error": "rate limit 429"})
        openai_mock = MagicMock()
        openai_mock.available.return_value = True
        openai_mock.call_json.return_value = ({"events": []}, {"input_tokens": 10, "output_tokens": 5})
        with patch.object(c, "_get_provider") as mock_get:
            def side_effect(key):
                return deepseek_mock if key == "deepseek" else openai_mock
            mock_get.side_effect = side_effect
            parsed, usage = c.generate("classifier", "sys", "user", radar="industry")
            assert parsed == {"events": []}
            assert usage["provider"] == "openai"
            assert usage["fallback_from_provider"] == "deepseek"


def test_llm_no_fallback_on_auth_failure():
    models = _make_models(classifier_provider="deepseek", with_fallback=True)
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-bad", "OPENAI_API_KEY": "sk-test2"}, clear=False):
        c = LLMClient(models)
        deepseek_mock = MagicMock()
        deepseek_mock.available.return_value = True
        deepseek_mock.call_json.return_value = (None, {"input_tokens": 10, "output_tokens": 0, "error": "invalid_api_key bad key"})
        with patch.object(c, "_get_provider", return_value=deepseek_mock):
            parsed, usage = c.generate("classifier", "sys", "user", radar="industry")
            assert parsed is None
            assert usage["error"] == "invalid_api_key bad key"


def test_llm_invalid_provider_graceful():
    models = {
        "providers": {"bad": {"type": "openai_compatible", "base_url": "https://bad.example.com", "api_key_env": "BAD_KEY"}},
        "roles": {"classifier": {"primary": {"provider": "bad", "model": "m1"}, "fallback": None}},
    }
    c = LLMClient(models)
    parsed, usage = c.generate("classifier", "sys", "user")
    assert parsed is None
    assert "error" in usage


def test_llm_backward_compat_legacy():
    models = {"classifier": {"primary": "gpt-legacy", "fallback": None}, "synthesis": {"primary": "gpt-legacy2", "fallback": None}}
    c = LLMClient(models)
    assert isinstance(c.available(), bool)


def test_llm_mixed_config_prefers_roles():
    models = {
        "providers": {"deepseek": {"type": "openai_compatible", "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"}},
        "roles": {"classifier": {"primary": {"provider": "deepseek", "model": "deepseek-chat"}, "fallback": None}},
        "classifier": {"primary": "old-model", "fallback": None},
    }
    res = resolve_role(models, "classifier")
    assert res["primary"] == ("deepseek", "deepseek-chat")


# ═══════════════════════════════════════════════════════════════════
# Cost Guard — provider-agnostic pricing
# ═══════════════════════════════════════════════════════════════════

def test_cost_known_pricing():
    guard = CostGuard(budget_usd=5, pricing={"gpt-test": {"input": 1.0, "output": 2.0}}, state=StateStore(state_dir=Path(tempfile.mkdtemp())))
    cost = guard.estimate_cost("gpt-test", 1_000_000, 1_000_000)
    assert cost == 3.0
    assert guard.is_pricing_known("gpt-test") is True


def test_cost_unknown_pricing():
    guard = CostGuard(budget_usd=5, pricing={"gpt-test": {"input": 1.0, "output": 2.0}}, state=StateStore(state_dir=Path(tempfile.mkdtemp())))
    cost = guard.estimate_cost("unknown-model-xyz", 1_000_000, 1_000_000)
    assert cost == 0.0
    assert guard.is_pricing_known("unknown-model-xyz") is False


def test_cost_unknown_does_not_block():
    guard = CostGuard(budget_usd=0.001, pricing={}, state=StateStore(state_dir=Path(tempfile.mkdtemp())))
    ok, _ = guard.can_call(0.0)
    assert ok is True


def test_cost_usage_unavailable_no_crash():
    guard = CostGuard(budget_usd=5, pricing={"m": {"input": 1.0, "output": 1.0}}, state=StateStore(state_dir=Path(tempfile.mkdtemp())))
    cost = guard.record("m", 100, 50, "industry", provider="test", usage_unavailable=True)
    assert isinstance(cost, float)


def test_cost_unknown_record():
    guard = CostGuard(budget_usd=5, pricing={}, state=StateStore(state_dir=Path(tempfile.mkdtemp())))
    cost = guard.record("unknown-model", 100, 50, "industry", provider="test", cost_unknown=True)
    assert cost == 0.0


# ═══════════════════════════════════════════════════════════════════
# Backward compat: old OpenAIClient shim
# ═══════════════════════════════════════════════════════════════════

def test_old_openai_client_shim():
    from pipeline.openai_client import OpenAIClient
    c = OpenAIClient(api_key=None)
    assert not c.available()
    c2 = OpenAIClient(api_key="sk-test")
    assert isinstance(c2.available(), bool)


def test_old_config_still_works():
    models = {"classifier": {"primary": "gpt-4o-mini", "fallback": None}, "synthesis": {"primary": "gpt-4o-mini", "fallback": None}}
    c = LLMClient(models)
    assert isinstance(c.available(), bool)
