from __future__ import annotations
import logging
import json
import httpx
from datetime import datetime, timezone
from radar.schema import Event, RadarType, EventType
from collectors.base import BaseCollector, CollectorResult

logger = logging.getLogger(__name__)

class AppStoreCollector(BaseCollector):
    """Fetch App Store version history via iTunes lookup + RSS."""
    def __init__(self, name: str, app_id: str | None = None, app_name: str | None = None, radar: str = "competitor", credibility: int = 90):
        self.name = name
        self.app_id = app_id
        self.app_name = app_name
        self.radar = radar
        self.credibility = credibility

    async def collect(self, client: httpx.AsyncClient) -> CollectorResult:
        if not self.app_id:
            # Need resolved id; if unresolved, skip gracefully
            return CollectorResult(events=[], source=self.name, success=True, error="unresolved app_id")
        try:
            # Lookup
            url = f"https://itunes.apple.com/lookup?id={self.app_id}"
            resp = await client.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if not results:
                return CollectorResult(events=[], source=self.name, success=False, error="no app found")
            app = results[0]
            version = app.get("version","")
            notes = app.get("releaseNotes") or ""
            track_url = app.get("trackViewUrl") or f"https://apps.apple.com/app/id{self.app_id}"
            # version history not fully available via lookup, but we get current version notes
            if not notes:
                notes = version
            eid = Event.make_id(track_url+f"#{version}", f"{self.name} {version}")
            ev = Event(event_id=eid, radar=RadarType(self.radar), source=self.name, source_url=track_url,
                       title=f"{self.name} v{version} - App Store", excerpt=notes[:500],
                       event_type=EventType.app_update, credibility=self.credibility, entity=self.name)
            return CollectorResult(events=[ev] if notes else [], source=self.name, success=True)
        except Exception as e:
            return CollectorResult(events=[], source=self.name, success=False, error=str(e))

async def resolve_app_store_id(client: httpx.AsyncClient, app_name: str, expected_domain: str | None = None) -> dict:
    """Search iTunes for app_name, return best match with score."""
    try:
        from urllib.parse import quote
        url = f"https://itunes.apple.com/search?term={quote(app_name)}&entity=software&limit=10"
        resp = await client.get(url, timeout=8)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        best = None
        best_score = 0
        for r in results:
            score = 0
            track = (r.get("trackName") or "").lower()
            seller = (r.get("sellerName") or "").lower()
            app_lower = app_name.lower()
            if app_lower in track:
                score += 50
            if track == app_lower:
                score += 30
            if expected_domain and expected_domain.lower() in (r.get("sellerUrl") or "").lower():
                score += 40
            # Prefer wallet category
            if "wallet" in track:
                score += 10
            if score > best_score:
                best_score = score
                best = r
        if best and best_score >= 50:
            return {"app_id": str(best["trackId"]), "score": best_score, "match": best.get("trackName"), "seller": best.get("sellerName"), "resolved": True}
        return {"resolved": False, "score": best_score, "candidates": len(results)}
    except Exception as e:
        return {"resolved": False, "error": str(e)}
