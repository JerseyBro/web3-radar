from __future__ import annotations
import logging
from datetime import datetime, timezone
import httpx
from radar.schema import Event, RadarType, EventType
from collectors.base import BaseCollector, CollectorResult
from pipeline.normalize import excerpt_from_html

logger = logging.getLogger(__name__)

class WebCollector(BaseCollector):
    """Generic web scraper for official blogs that don't offer RSS."""
    def __init__(self, name: str, url: str, radar: str = "industry", credibility: int = 70, selector: str = "a"):
        self.name = name
        self.url = url
        self.radar = radar
        self.credibility = credibility
        self.selector = selector

    async def collect(self, client: httpx.AsyncClient) -> CollectorResult:
        try:
            resp = await client.get(self.url, timeout=self.timeout, follow_redirects=True, headers={"User-Agent":"web3-radar/1.0"})
            resp.raise_for_status()
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            links = soup.select(self.selector)[:15]
            events = []
            for a in links:
                href = a.get("href") or ""
                title = a.get_text(strip=True)
                if not href or not title or len(title) < 8:
                    continue
                if href.startswith("/"):
                    from urllib.parse import urljoin
                    href = urljoin(self.url, href)
                if not href.startswith("http"):
                    continue
                eid = Event.make_id(href, title)
                ev = Event(event_id=eid, radar=RadarType(self.radar), source=self.name, source_url=href,
                           title=title, excerpt=title[:300], event_type=EventType.blog_post, credibility=self.credibility)
                events.append(ev)
            return CollectorResult(events=events, source=self.name, success=True)
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))
