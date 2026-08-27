from __future__ import annotations
import logging
import re
import httpx
from radar.schema import Event, RadarType, EventType
from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

class GooglePlayCollector(BaseCollector):
    def __init__(self, name: str, package_id: str | None = None, radar: str = "competitor", credibility: int = 85):
        self.name = name
        self.package_id = package_id
        self.radar = radar
        self.credibility = credibility

    async def collect(self, client: httpx.AsyncClient) -> CollectorResult:
        if not self.package_id:
            return CollectorResult(events=[], source=self.name, success=True, error="unresolved package_id")
        try:
            url = f"https://play.google.com/store/apps/details?id={self.package_id}&hl=en_US"
            resp = await client.get(url, timeout=self.timeout, follow_redirects=True, headers={"User-Agent":"Mozilla/5.0 web3-radar/1.0"})
            if resp.status_code != 200:
                return CollectorResult(events=[], source=self.name, success=False, error=f"status {resp.status_code}")
            html = resp.text
            # Extract "What's New" / release notes via regex fallback
            # Play pages are JS-heavy; try simple patterns
            notes = ""
            # Try to find whatsNew
            m = re.search(r'"whatsNew"\s*:\s*"([^"]+)"', html)
            if m:
                notes = m.group(1).encode().decode('unicode_escape')[:500]
            if not notes:
                # fallback: look for Recent changes section
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                # Find version string
                vm = re.search(r"Updated on.*?(Bug fixes|Performance|Version|Update)[^.]*\.", text)
                if vm:
                    notes = vm.group(0)[:500]
                else:
                    notes = text[:500]
            link = f"https://play.google.com/store/apps/details?id={self.package_id}"
            # Extract version if possible
            ver = ""
            vm2 = re.search(r"\[\[\"([0-9]+\.[0-9.]+)\"\]\]", html)
            if vm2:
                ver = vm2.group(1)
            title = f"{self.name} {ver} - Google Play" if ver else f"{self.name} - Google Play"
            eid = Event.make_id(link+f"#{ver}", title)
            ev = Event(event_id=eid, radar=RadarType(self.radar), source=self.name, source_url=link,
                       title=title, excerpt=notes[:500], event_type=EventType.app_update, credibility=self.credibility, entity=self.name)
            return CollectorResult(events=[ev] if notes else [], source=self.name, success=True)
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))

async def resolve_google_play_id(client: httpx.AsyncClient, app_name: str, expected_package: str | None = None) -> dict:
    """Simple validation: check if expected_package page exists and title matches."""
    if not expected_package:
        return {"resolved": False, "reason": "no candidate package"}
    try:
        url = f"https://play.google.com/store/apps/details?id={expected_package}&hl=en_US"
        resp = await client.get(url, timeout=8, follow_redirects=True, headers={"User-Agent":"Mozilla/5.0"})
        if resp.status_code == 200 and app_name.lower().split()[0] in resp.text.lower():
            return {"package_id": expected_package, "resolved": True, "score": 80}
        return {"resolved": False, "score": 30}
    except Exception as e:
        return {"resolved": False, "error": str(e)}
