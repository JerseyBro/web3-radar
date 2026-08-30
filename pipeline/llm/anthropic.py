"""Anthropic Claude native Messages API provider adapter.

Uses the `anthropic` SDK. Not OpenAI-compatible — implements its own
Messages API mapping while exposing the same LLMProvider interface
so business code stays provider-agnostic.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pipeline.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        provider_name: str = "anthropic",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30,
        max_retries: int = 3,
    ):
        self.provider_name = provider_name
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None
        if api_key:
            try:
                import anthropic

                kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout, "max_retries": 0}
                if base_url:
                    kwargs["base_url"] = base_url
                self._client = anthropic.Anthropic(**kwargs)
            except Exception as e:
                logger.warning(f"[{provider_name}] Anthropic SDK init failed: {e}")

    def available(self) -> bool:
        return self._client is not None

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
    ) -> tuple[dict | None, dict]:
        if not self._client:
            return None, {"input_tokens": 0, "output_tokens": 0, "error": "no client"}

        # Anthropic prefers JSON hint in the user message, not response_format
        user_with_hint = user
        if schema is not None:
            user_with_hint = user + "\n\nRespond with valid JSON only."

        est_input = self._estimate_tokens(system + user_with_hint)
        last_err: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                resp = self._client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system,
                    messages=[{"role": "user", "content": user_with_hint}],
                )

                # Extract text from content blocks
                content = ""
                for block in getattr(resp, "content", []):
                    if getattr(block, "type", None) == "text":
                        content += getattr(block, "text", "")

                if not content:
                    content = "{}"

                usage: dict[str, Any] = {}
                raw_usage = getattr(resp, "usage", None)
                if raw_usage is not None:
                    usage["input_tokens"] = getattr(raw_usage, "input_tokens", est_input)
                    usage["output_tokens"] = getattr(raw_usage, "output_tokens", self._estimate_tokens(content))
                else:
                    usage["input_tokens"] = est_input
                    usage["output_tokens"] = self._estimate_tokens(content)
                    usage["usage_unavailable"] = True

                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"[{self.provider_name}] JSON parse failed: {e} content={content[:500]}")
                    return None, {**usage, "error": "json_parse_failed"}

                return parsed, usage

            except Exception as e:
                last_err = e
                msg = str(e).lower()
                retryable = any(
                    k in msg
                    for k in [
                        "timeout",
                        "rate limit",
                        "429",
                        "500",
                        "502",
                        "503",
                        "504",
                        "connection",
                        "overloaded",
                    ]
                )
                if not retryable and attempt == 0:
                    logger.error(f"[{self.provider_name}] non-retryable: {e}")
                    break
                if attempt < self.max_retries - 1:
                    sleep = (2 ** attempt) * 1.0
                    time.sleep(sleep)
                else:
                    logger.error(f"[{self.provider_name}] failed after {self.max_retries}: {e}")

        return None, {"input_tokens": est_input, "output_tokens": 0, "error": str(last_err) if last_err else "unknown"}
