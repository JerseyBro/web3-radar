from __future__ import annotations
import logging
from datetime import datetime, timezone
import httpx
import feedparser
from radar.schema import Event, RadarType, EventType
from collectors.base import BaseCollector, CollectorResult
from pipeline.normalize import excerpt_from_html
from radar.schema import Event as Ev

logger = logging.getLogger(__name__)

class RSSCollector(BaseCollector):
    def __init__(self, name: str, url: str, radar: str = "industry", credibility: int = 70):
        self.name = name
        self.url = url
        self.radar = radar
        self.credibility = credibility

    async def collect(self, client: httpx.AsyncClient) -> CollectorResult:
        try:
            resp = await client.get(self.url, timeout=self.timeout, follow_redirects=True, headers={"User-Agent":"web3-radar/1.0"})
            resp.raise_for_status()
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))
        feed = feedparser.parse(resp.content)
        events: list[Ev] = []
        for entry in feed.entries[:20]:
            link = getattr(entry, "link", "") or self.url
            title = getattr(entry, "title", "") or "Untitled"
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    import calendar
                    ts = calendar.timegm(entry.published_parsed)
                    published = datetime.fromtimestamp(ts, tz=timezone.utc)
                except: pass
            eid = Ev.make_id(link, title)
            excerpt = excerpt_from_html(summary) if "<" in summary else summary[:400]
            ev = Ev(
                event_id=eid, radar=RadarType(self.radar), source=self.name, source_url=link,
                title=title.strip(), published_at=published, excerpt=excerpt,
                event_type=EventType.blog_post if "blog" in self.name.lower() else EventType.news,
                credibility=self.credibility,
            )
            events.append(ev)
        return CollectorResult(events=events, source=self.name, success=True)
