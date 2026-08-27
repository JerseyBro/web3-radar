from __future__ import annotations
import os
import logging
import httpx
from datetime import datetime, timezone
from dateutil import parser as dateparser
from radar.schema import Event, RadarType, EventType
from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

class GitHubCollector(BaseCollector):
    def __init__(self, name: str, repo: str, radar: str = "competitor", credibility: int = 85):
        # repo like "ethereum/EIPs" or "RabbyHub/rabby"
        self.name = name
        self.repo = repo.strip("/")
        self.radar = radar
        self.credibility = credibility

    async def collect(self, client: httpx.AsyncClient) -> CollectorResult:
        token = os.getenv("GITHUB_TOKEN")
        headers = {"User-Agent":"web3-radar/1.0", "Accept":"application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        url = f"https://api.github.com/repos/{self.repo}/releases"
        try:
            resp = await client.get(url, headers=headers, timeout=self.timeout)
            if resp.status_code == 404:
                # try tags fallback
                url2 = f"https://api.github.com/repos/{self.repo}/tags"
                resp = await client.get(url2, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()[:10]
                events = []
                for t in data:
                    name = t.get("name","")
                    link = f"https://github.com/{self.repo}/releases/tag/{name}"
                    eid = Event.make_id(link, name)
                    ev = Event(event_id=eid, radar=RadarType(self.radar), source=self.name, source_url=link,
                               title=f"{self.repo} {name}", excerpt=name, event_type=EventType.github_release, credibility=self.credibility, entity=self.name)
                    events.append(ev)
                return CollectorResult(events=events, source=self.name, success=True)
            resp.raise_for_status()
            data = resp.json()[:10]
            events = []
            for r in data:
                title = r.get("name") or r.get("tag_name") or "Release"
                body = (r.get("body") or "")[:400]
                link = r.get("html_url") or f"https://github.com/{self.repo}/releases"
                pub = None
                if r.get("published_at"):
                    try: pub = dateparser.parse(r["published_at"])
                    except: pass
                eid = Event.make_id(link, title)
                ev = Event(event_id=eid, radar=RadarType(self.radar), source=self.name, source_url=link,
                           title=title, excerpt=body, event_type=EventType.github_release, published_at=pub,
                           credibility=self.credibility, entity=self.name)
                events.append(ev)
            return CollectorResult(events=events, source=self.name, success=True)
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))
