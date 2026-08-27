from __future__ import annotations
import httpx
from radar.schema import Event, RadarType, EventType
from collectors.base import BaseCollector, CollectorResult

class DefiLlamaCollector(BaseCollector):
    name = "DeFiLlama"

    def __init__(self, credibility: int = 90):
        self.credibility = credibility

    async def collect(self, client: httpx.AsyncClient) -> CollectorResult:
        try:
            resp = await client.get("https://api.llama.fi/chains", timeout=self.timeout)
            resp.raise_for_status()
            chains = resp.json()
            # Create summary events for top movers
            # chains is list of {name, tvl, change_1d ...}
            # Sort by tvl change
            try:
                sorted_chains = sorted(chains, key=lambda x: abs(x.get("change_1d") or 0), reverse=True)[:5]
            except:
                sorted_chains = chains[:5]
            events = []
            for c in sorted_chains:
                name = c.get("name","unknown")
                tvl = c.get("tvl",0)
                chg = c.get("change_1d")
                title = f"TVL {name}: ${tvl:,.0f} ({chg:+.1f}% 24h)" if chg is not None else f"TVL {name}: ${tvl:,.0f}"
                eid = Event.make_id(f"https://defillama.com/chain/{name}", title)
                ev = Event(event_id=eid, radar=RadarType.industry, source="DeFiLlama", source_url=f"https://defillama.com/chain/{name}",
                           title=title, excerpt=f"Chain {name} TVL snapshot", event_type=EventType.defi_metric,
                           credibility=self.credibility, tags=["tvl","chain"])
                # heuristic money flow significance
                if chg is not None and abs(chg) > 5:
                    ev.money_flow_significance = 80
                    ev.impact = 70
                events.append(ev)
            return CollectorResult(events=events, source=self.name, success=True)
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))
