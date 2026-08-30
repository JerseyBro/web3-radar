"""Abstract provider interface for multi-provider LLM layer."""

from __future__ import annotations

import abc
from typing import Any


class LLMProvider(abc.ABC):
    """Thin provider contract — text in, text/JSON out."""

    provider_name: str = "unknown"

    @abc.abstractmethod
    def available(self) -> bool:
        """Whether this provider can make calls (key + SDK present)."""

    @abc.abstractmethod
    def call_json(
        self,
        model: str,
        system: str,
        user: str,
        schema: dict | None = None,
        radar: str = "industry",
    ) -> tuple[dict | None, dict]:
        """Call provider with structured JSON hint.

        Returns (parsed_json_or_None, usage_dict).
        usage_dict always contains at least: input_tokens, output_tokens.
        On failure it also contains 'error'.
        Optional: 'cost_unknown', 'usage_unavailable' flags.
        Never logs the API key.
        """

    def model_available(self, model: str | None) -> bool:
        if not model:
            return False
        return self.available()
