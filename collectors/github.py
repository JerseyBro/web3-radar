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
                return CollectorResult(events=[], source=self.name, success=False, error="repository not found")
            resp.raise_for_status()
            data = resp.json()[:10]
            if not data:
                return await self._collect_commits(client, headers)
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

    async def _collect_commits(self, client: httpx.AsyncClient, headers: dict) -> CollectorResult:
        """Use dated repository activity when a repository has no Releases.

        Tags do not contain timestamps, so they cannot safely pass the weekly
        window. Recent commits provide a traceable, dated fallback instead.
        """
        url = f"https://api.github.com/repos/{self.repo}/commits?per_page=10"
        try:
            resp = await client.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            events = []
            for item in resp.json()[:10]:
                commit = item.get("commit") or {}
                message = (commit.get("message") or "Commit").splitlines()[0]
                link = item.get("html_url") or f"https://github.com/{self.repo}/commits"
                author = commit.get("author") or commit.get("committer") or {}
                published = None
                if author.get("date"):
                    try:
                        published = dateparser.parse(author["date"])
                    except (TypeError, ValueError, OverflowError):
                        published = None
                eid = Event.make_id(link, message)
                events.append(Event(
                    event_id=eid,
                    radar=RadarType(self.radar),
                    source=self.name,
                    source_url=link,
                    title=f"{self.repo}: {message}",
                    excerpt=message[:400],
                    event_type=EventType.docs_update,
                    published_at=published,
                    credibility=self.credibility,
                    entity=self.name,
                    raw_meta={"sha": item.get("sha", "")},
                ))
            return CollectorResult(events=events, source=self.name, success=True)
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))


class GitHubOrgCollector(BaseCollector):
    """Collect dated public activity for an organization without guessing repositories."""

    def __init__(self, name: str, org: str, radar: str = "competitor", credibility: int = 75):
        self.name = name
        self.org = org.strip("/")
        self.radar = radar
        self.credibility = credibility

    async def collect(self, client: httpx.AsyncClient) -> CollectorResult:
        token = os.getenv("GITHUB_TOKEN")
        headers = {"User-Agent": "web3-radar/1.0", "Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        urls = [
            f"https://api.github.com/orgs/{self.org}/events?per_page=30",
            f"https://api.github.com/users/{self.org}/events/public?per_page=30",
        ]
        try:
            response = None
            for url in urls:
                response = await client.get(url, headers=headers, timeout=self.timeout)
                if response.status_code != 404:
                    break
            assert response is not None
            response.raise_for_status()
            events: list[Event] = []
            for item in response.json():
                event = self._from_public_event(item)
                if event is not None:
                    events.append(event)
                if len(events) >= 15:
                    break
            return CollectorResult(events=events, source=self.name, success=True)
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))

    def _from_public_event(self, item: dict) -> Event | None:
        event_type = item.get("type")
        if event_type not in {"ReleaseEvent", "PushEvent"}:
            return None
        repo = (item.get("repo") or {}).get("name") or self.org
        payload = item.get("payload") or {}
        published = None
        if item.get("created_at"):
            try:
                published = dateparser.parse(item["created_at"])
            except (TypeError, ValueError, OverflowError):
                published = None

        if event_type == "ReleaseEvent":
            release = payload.get("release") or {}
            title = release.get("name") or release.get("tag_name") or "Release"
            link = release.get("html_url") or f"https://github.com/{repo}/releases"
            excerpt = (release.get("body") or title)[:400]
            schema_type = EventType.github_release
        else:
            commits = payload.get("commits") or []
            message = ((commits[0].get("message") if commits else None) or "Repository update").splitlines()[0]
            count = len(commits) or int(payload.get("size") or 1)
            title = f"{repo}: {message}"
            head = payload.get("head")
            link = f"https://github.com/{repo}/commit/{head}" if head else f"https://github.com/{repo}/commits"
            excerpt = f"{count} commit(s) pushed; {message}"[:400]
            schema_type = EventType.docs_update

        event_id = Event.make_id(link, f"{title}|{item.get('id', '')}")
        return Event(
            event_id=event_id,
            radar=RadarType(self.radar),
            source=self.name,
            source_url=link,
            title=title,
            published_at=published,
            excerpt=excerpt,
            event_type=schema_type,
            credibility=self.credibility,
            entity=self.name,
            raw_meta={"github_event_id": item.get("id", ""), "github_event_type": event_type},
        )
