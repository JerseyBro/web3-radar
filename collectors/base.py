from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import AsyncGenerator
import httpx
from radar.schema import Event

logger = logging.getLogger(__name__)

@dataclass
class CollectorResult:
    events: list[Event]
    source: str
    success: bool
    error: str | None = None

class BaseCollector:
    name: str = "base"
    timeout: float = 15.0

    async def collect(self, client: httpx.AsyncClient) -> CollectorResult:
        raise NotImplementedError

    async def safe_collect(self, client: httpx.AsyncClient) -> CollectorResult:
        try:
            return await self.collect(client)
        except Exception as e:
            logger.warning(f"Collector {self.name} failed: {e}")
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))

async def collect_all(collectors: list[BaseCollector], client: httpx.AsyncClient) -> list[CollectorResult]:
    import asyncio
    tasks = [c.safe_collect(client) for c in collectors]
    return await asyncio.gather(*tasks)
