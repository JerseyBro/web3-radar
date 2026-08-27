import httpx
from collectors.base import BaseCollector, CollectorResult, collect_all

class FailCollector(BaseCollector):
    name="fail"
    async def collect(self, client): raise RuntimeError("boom")

class OkCollector(BaseCollector):
    name="ok"
    async def collect(self, client):
        from radar.schema import Event, RadarType
        e = Event(event_id="1", radar=RadarType.industry, source="ok", source_url="https://example.com", title="ok")
        return CollectorResult(events=[e], source="ok", success=True)

async def test_isolation():
    async with httpx.AsyncClient() as client:
        results = await collect_all([FailCollector(), OkCollector()], client)
        assert len(results)==2
        assert results[0].success==False
        assert results[1].success==True
        assert len(results[1].events)==1
