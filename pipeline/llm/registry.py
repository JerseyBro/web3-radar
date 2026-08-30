"""Provider registry — resolves provider defs from config/models.yaml.

Supports both new format (providers + roles) and legacy format
(classifier.primary as plain model string) for backward compatibility.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pipeline.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ── Built-in provider definitions ─────────────────────────────────
# Each entry maps a provider key in config/models.yaml -> {type, default base_url}
# The api_key_env can be overridden per-entry in user config.
PROVIDER_DEFS: dict[str, dict[str, str]] = {
    "openai": {
        "type": "openai_compatible",
        "default_base_url": "https://api.openai.com/v1",
        "default_api_key_env": "OPENAI_API_KEY",
    },
    "deepseek": {
        "type": "openai_compatible",
        "default_base_url": "https://api.deepseek.com",
        "default_api_key_env": "DEEPSEEK_API_KEY",
    },
    "anthropic": {
        "type": "anthropic",
        "default_base_url": "https://api.anthropic.com",
        "default_api_key_env": "ANTHROPIC_API_KEY",
    },
    "alibaba": {
        "type": "openai_compatible",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_api_key_env": "DASHSCOPE_API_KEY",
    },
    "dashscope": {
        "type": "openai_compatible",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_api_key_env": "DASHSCOPE_API_KEY",
    },
    "tencent": {
        "type": "openai_compatible",
        "default_base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "default_api_key_env": "TENCENT_LLM_API_KEY",
    },
    "volcengine": {
        "type": "openai_compatible",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_api_key_env": "VOLCENGINE_API_KEY",
    },
    "opencode_go": {
        "type": "openai_compatible",
        "default_base_url": "https://opencode.ai/zen/go/v1",
        "default_api_key_env": "OPENCODE_GO_API_KEY",
    },
    "generic": {
        "type": "openai_compatible",
        "default_base_url": "",
        "default_api_key_env": "CUSTOM_LLM_API_KEY",
    },
}


def _resolve_provider_config(
    provider_key: str,
    user_providers: dict[str, Any],
) -> dict[str, str]:
    """Merge user config for a provider with built-in defaults."""
    builtin = PROVIDER_DEFS.get(provider_key, {"type": "openai_compatible", "default_base_url": "", "default_api_key_env": f"{provider_key.upper()}_API_KEY"})
    user_cfg = user_providers.get(provider_key, {}) or {}
    ptype = user_cfg.get("type") or builtin["type"]
    base_url = user_cfg.get("base_url") or builtin["default_base_url"]
    api_key_env = user_cfg.get("api_key_env") or builtin["default_api_key_env"]
    # Allow OPENAI_BASE_URL env override for openai provider (backward compat)
    if provider_key == "openai":
        env_base = os.getenv("OPENAI_BASE_URL")
        if env_base:
            base_url = env_base
    return {"type": ptype, "base_url": base_url, "api_key_env": api_key_env}


def build_provider(provider_key: str, user_providers: dict[str, Any]) -> LLMProvider:
    """Instantiate a provider from config. Returns unavailable provider if key missing."""
    cfg = _resolve_provider_config(provider_key, user_providers)
    ptype = cfg["type"]
    api_key = os.getenv(cfg["api_key_env"], "") or None
    base_url = cfg["base_url"] or None

    if ptype == "anthropic":
        from pipeline.llm.anthropic import AnthropicProvider

        return AnthropicProvider(provider_name=provider_key, api_key=api_key, base_url=base_url)
    else:
        from pipeline.llm.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(provider_name=provider_key, api_key=api_key, base_url=base_url)


def get_provider(provider_key: str, models_config: dict) -> LLMProvider:
    """Convenience: build provider from full models.yaml dict."""
    user_providers = models_config.get("providers", {}) or {}
    return build_provider(provider_key, user_providers)


def list_providers(models_config: dict) -> list[str]:
    user_providers = models_config.get("providers", {}) or {}
    if user_providers:
        return sorted(user_providers.keys())
    return ["openai"]


# ── Config helpers ────────────────────────────────────────────────

def _is_new_role_format(models: dict) -> bool:
    """True if config uses providers/roles, False if legacy flat classifier/synthesis."""
    return "providers" in models or "roles" in models


def _slot_to_provider_model(slot: Any, default_provider: str = "openai") -> tuple[str, str] | None:
    """Normalize a classifier/synthesis slot to (provider, model).

    Accepts:
      - None / "" -> None
      - "gpt-4o-mini" (plain string, legacy) -> (default_provider, "gpt-4o-mini")
      - {"provider": "deepseek", "model": "deepseek-chat"} -> ("deepseek", "deepseek-chat")
      - {"model": "gpt-4o-mini"} -> (default_provider, "gpt-4o-mini")
    """
    if slot is None or slot == "":
        return None
    if isinstance(slot, str):
        return (default_provider, slot)
    if isinstance(slot, dict):
        model = slot.get("model")
        if not model:
            return None
        provider = slot.get("provider") or default_provider
        return (provider, model)
    return None


def resolve_role(models: dict, role: str) -> dict:
    """Resolve a role (classifier/synthesis) to {primary, fallback} as (provider, model) tuples.

    Handles both legacy and new config formats.
    """
    # New format: roles.classifier.primary = {provider, model}
    roles = models.get("roles")
    if roles and role in roles:
        cfg = roles[role] or {}
        return {
            "primary": _slot_to_provider_model(cfg.get("primary")),
            "fallback": _slot_to_provider_model(cfg.get("fallback")),
        }

    # Legacy format: classifier.primary = "gpt-5.6-luna" (string) or null
    cfg = models.get(role, {}) or {}
    return {
        "primary": _slot_to_provider_model(cfg.get("primary")),
        "fallback": _slot_to_provider_model(cfg.get("fallback")),
    }


def required_api_key_envs(models: dict) -> set[str]:
    """Return the set of api_key_env vars actually needed by classifier/synthesis (incl. fallback)."""
    user_providers = models.get("providers", {}) or {}
    needed_providers: set[str] = set()
    for role in ("classifier", "synthesis"):
        resolved = resolve_role(models, role)
        for slot in ("primary", "fallback"):
            pm = resolved.get(slot)
            if pm:
                needed_providers.add(pm[0])

    envs: set[str] = set()
    for pk in needed_providers:
        cfg = _resolve_provider_config(pk, user_providers)
        envs.add(cfg["api_key_env"])
    return envs


def all_known_api_key_envs(models: dict) -> set[str]:
    """All env vars for every provider defined (for display as OPTIONAL/UNUSED)."""
    user_providers = models.get("providers", {}) or {}
    keys = set(PROVIDER_DEFS.keys()) | set(user_providers.keys())
    envs: set[str] = set()
    for pk in keys:
        cfg = _resolve_provider_config(pk, user_providers)
        envs.add(cfg["api_key_env"])
    return envs
