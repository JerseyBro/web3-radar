from __future__ import annotations
import httpx
from radar.schema import Event, RadarType, EventType
from collectors.base import BaseCollector, CollectorResult

class CoinGeckoCollector(BaseCollector):
    name = "CoinGecko"

    def __init__(self, credibility: int = 80):
        self.credibility = credibility

    async def collect(self, client: httpx.AsyncClient) -> CollectorResult:
        try:
            resp = await client.get("https://api.coingecko.com/api/v3/search/trending", timeout=self.timeout, headers={"User-Agent":"web3-radar/1.0"})
            if resp.status_code == 429:
                return CollectorResult(events=[], source=self.name, success=False, error="rate limited")
            resp.raise_for_status()
            data = resp.json()
            coins = data.get("coins", [])[:7]
            events = []
            for c in coins:
                item = c.get("item", {})
                name = item.get("name","")
                symbol = item.get("symbol","")
                # trending is not high-signal; create low-weight events
                title = f"Trending: {name} ({symbol})"
                url = f"https://www.coingecko.com/en/coins/{item.get('id','')}"
                eid = Event.make_id(url, title)
                ev = Event(event_id=eid, radar=RadarType.industry, source="CoinGecko", source_url=url,
                           title=title, excerpt=f"{name} trending on CoinGecko", event_type=EventType.market_data,
                           credibility=self.credibility, tags=["trending","market"])
                ev.novelty = 40
                ev.impact = 30
                events.append(ev)
            return CollectorResult(events=events, source=self.name, success=True)
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))
