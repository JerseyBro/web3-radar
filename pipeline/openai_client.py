"""Backward-compatible shim — delegates to pipeline.llm.OpenAICompatibleProvider.

New code should import from pipeline.llm instead:
    from pipeline.llm import LLMClient
    from pipeline.llm.openai_compatible import OpenAICompatibleProvider
"""

from __future__ import annotations

from pipeline.llm.openai_compatible import OpenAICompatibleProvider


class OpenAIClient(OpenAICompatibleProvider):
    """Legacy alias. Accepts old signature OpenAIClient(api_key, base_url, ...)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30,
        max_retries: int = 3,
        provider_name: str = "openai",
        **kwargs,
    ):
        super().__init__(
            provider_name=provider_name,
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
