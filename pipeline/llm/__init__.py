"""Multi-provider LLM adapter layer.

Business code (radars/, pipeline/analyze.py) imports only:
    from pipeline.llm import LLMClient, get_llm_client

Provider routing, fallback, and secret resolution live in this package.
"""

from pipeline.llm.client import LLMClient, get_llm_client
from pipeline.llm.registry import get_provider, list_providers, PROVIDER_DEFS

__all__ = ["LLMClient", "get_llm_client", "get_provider", "list_providers", "PROVIDER_DEFS"]
