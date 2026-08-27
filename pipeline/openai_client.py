from __future__ import annotations
import json
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)

class OpenAIClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 30, max_retries: int = 3):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None
        if api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
            except Exception as e:
                logger.warning(f"OpenAI init failed: {e}")

    def available(self) -> bool:
        return self._client is not None

    def model_available(self, model: str | None = None) -> bool:
        # We cannot reliably list models offline; assume a configured, non-empty model
        # is available when a client exists. Without a client, nothing is available.
        return self._client is not None

    def _estimate_tokens(self, text: str) -> int:
        # rough: 1 token ~ 4 chars
        return max(1, len(text)//4)

    def call_json(self, model: str, system: str, user: str, schema: dict | None = None, radar: str = "industry") -> tuple[dict | None, dict]:
        """Call OpenAI with structured JSON output. Returns (parsed_json, usage)."""
        if not self._client:
            return None, {"input_tokens":0,"output_tokens":0,"error":"no client"}
        prompt = system + "\n\n" + user
        est_input = self._estimate_tokens(prompt)
        last_err = None
        for attempt in range(self.max_retries):
            try:
                # Prefer Responses API with structured outputs; fallback to chat.completions
                # Use chat.completions for broad compatibility
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role":"system","content":system},{"role":"user","content":user}],
                }
                if schema:
                    kwargs["response_format"] = {"type":"json_object"}
                resp = self._client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content or "{}"
                usage = {
                    "input_tokens": getattr(resp.usage, "prompt_tokens", est_input) if resp.usage else est_input,
                    "output_tokens": getattr(resp.usage, "completion_tokens", self._estimate_tokens(content)) if resp.usage else self._estimate_tokens(content),
                }
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON parse failed: {e} content={content[:500]}")
                    return None, {**usage, "error": "json_parse_failed"}
                return parsed, usage
            except Exception as e:
                last_err = e
                # Classify retryable
                msg = str(e).lower()
                retryable = any(k in msg for k in ["timeout","rate limit","429","500","502","503","504","connection"])
                if not retryable and attempt == 0:
                    logger.error(f"OpenAI non-retryable: {e}")
                    break
                if attempt < self.max_retries - 1:
                    sleep = (2 ** attempt) * 1.0
                    time.sleep(sleep)
                else:
                    logger.error(f"OpenAI failed after {self.max_retries}: {e}")
        return None, {"input_tokens": est_input, "output_tokens": 0, "error": str(last_err) if last_err else "unknown"}
