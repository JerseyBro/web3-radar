"""Unified LLM client — provider-agnostic facade for business code.

Business layers (pipeline/analyze.py, radar/cli.py, radar/ai_test.py)
import only this module. Provider branching stays inside this file.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pipeline.llm.registry import (
    resolve_role,
    required_api_key_envs,
    build_provider,
    PROVIDER_DEFS,
)
from pipeline.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ── Retry classification ──────────────────────────────────────────
# Fallback is only for provider-side transient failures, never for
# bad config / bad auth / budget exceeded.

NON_RETRYABLE_MARKERS = (
    "invalid_api_key",
    "invalid api key",
    "incorrect api key",
    "unauthorized",
    "authentication",
    "permission_denied",
    "billing",
    "budget exceeded",
    "invalid_request",
    "model_not_found",
    "unknown model",
)

RETRYABLE_MARKERS = (
    "timeout",
    "rate limit",
    "429",
    "500",
    "502",
    "503",
    "504",
    "connection",
    "overloaded",
)


def _is_fallback_eligible(error: str | None) -> bool:
    if not error:
        return False
    low = error.lower()
    if any(m in low for m in NON_RETRYABLE_MARKERS):
        return False
    # Budget exceeded should also not fallback at LLM layer (handled by CostGuard)
    if "budget" in low:
        return False
    return any(m in low for m in RETRYABLE_MARKERS) or "error" in low


def _log_fallback(from_provider: str, from_model: str, to_provider: str, to_model: str, reason: str) -> None:
    logger.warning(
        f"MODEL_FALLBACK from_provider={from_provider} from_model={from_model} "
        f"to_provider={to_provider} to_model={to_model} reason={reason}"
    )


class LLMClient:
    """Holds a cache of instantiated providers for a given models config."""

    def __init__(self, models: dict):
        self.models = models
        self._providers: dict[str, LLMProvider] = {}
        user_providers = models.get("providers", {}) or {}
        # Providers dict may be absent (legacy config) — that's fine, build_provider handles it
        self._user_providers = user_providers

    def _get_provider(self, provider_key: str) -> LLMProvider:
        if provider_key not in self._providers:
            self._providers[provider_key] = build_provider(provider_key, self._user_providers)
        return self._providers[provider_key]

    def available(self, provider_key: str | None = None) -> bool:
        """Overall available, or per-provider if provider_key given."""
        if provider_key:
            return self._get_provider(provider_key).available()
        # Any required provider available?
        for env in required_api_key_envs(self.models):
            if os.getenv(env):
                # At least one required key set — check if its provider is instantiable
                pass
        # Check that at least one provider in required set is available
        for role in ("classifier", "synthesis"):
            resolved = resolve_role(self.models, role)
            pm = resolved.get("primary") or resolved.get("fallback")
            if pm and self._get_provider(pm[0]).available():
                return True
        return False

    def model_available(self, model: str, provider: str = "openai") -> bool:
        return self._get_provider(provider).model_available(model)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    def call_json(
        self,
        model: str,
        system: str,
        user: str,
        schema: dict | None = None,
        radar: str = "industry",
        provider: str = "openai",
    ) -> tuple[dict | None, dict]:
        """Call a specific provider+model. Thin wrapper over provider.call_json."""
        p = self._get_provider(provider)
        return p.call_json(model, system, user, schema=schema, radar=radar)

    def generate(
        self,
        role: str,
        system: str,
        user: str,
        schema: dict | None = None,
        radar: str = "industry",
    ) -> tuple[dict | None, dict]:
        """Role-based generate with cross-provider fallback.

        Resolves role -> primary (provider, model) -> calls it.
        On retryable failure, falls back to fallback (provider, model) if configured.
        Returns (parsed_json_or_None, usage_dict) where usage includes
        provider/model metadata.
        """
        resolved = resolve_role(self.models, role)
        primary = resolved.get("primary")
        fallback = resolved.get("fallback")

        if primary is None:
            return None, {"input_tokens": 0, "output_tokens": 0, "error": "no primary model configured"}

        p_provider, p_model = primary
        p = self._get_provider(p_provider)

        # If primary provider not available (no key), try fallback directly
        if not p.available():
            if fallback:
                f_provider, f_model = fallback
                _log_fallback(p_provider, p_model, f_provider, f_model, "primary provider unavailable")
                fp = self._get_provider(f_provider)
                if fp.available():
                    parsed, usage = fp.call_json(f_model, system, user, schema=schema, radar=radar)
                    usage["provider"] = f_provider
                    usage["model"] = f_model
                    return parsed, usage
            return None, {"input_tokens": 0, "output_tokens": 0, "error": f"provider {p_provider} unavailable"}

        parsed, usage = p.call_json(p_model, system, user, schema=schema, radar=radar)
        usage["provider"] = p_provider
        usage["model"] = p_model

        # Cross-provider fallback on retryable failure
        if parsed is None and fallback:
            err = usage.get("error", "")
            if _is_fallback_eligible(err):
                f_provider, f_model = fallback
                # Never fallback to same provider+model
                if not (f_provider == p_provider and f_model == p_model):
                    fp = self._get_provider(f_provider)
                    if fp.available():
                        _log_fallback(p_provider, p_model, f_provider, f_model, err or "unknown")
                        parsed2, usage2 = fp.call_json(f_model, system, user, schema=schema, radar=radar)
                        usage2["provider"] = f_provider
                        usage2["model"] = f_model
                        # Preserve fallback provenance
                        usage2["fallback_from_provider"] = p_provider
                        usage2["fallback_from_model"] = p_model
                        return parsed2, usage2

        return parsed, usage


def get_llm_client(models: dict | None = None) -> LLMClient:
    """Factory — reads models config if not given."""
    if models is not None:
        return LLMClient(models)
    from radar.config import get_settings

    return LLMClient(get_settings()["models"])
