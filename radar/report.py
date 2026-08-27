from __future__ import annotations
import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from radar.schema import Event


def make_report_id(radar: str, period: str, kind: str = "weekly") -> str:
    raw = f"{radar}|{period}|{kind}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class Report:
    radar: str
    period: str            # e.g. 2026-W35
    kind: str = "weekly"   # weekly | critical | smoke
    id: str = ""
    title: str = ""
    markdown: str = ""
    events: list[Event] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    generated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = make_report_id(self.radar, self.period, self.kind)
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()
        if not self.title:
            self.title = f"{self.radar.capitalize()} {self.kind} report {self.period}"

    def canonical_json(self) -> dict:
        return {
            "schema_version": "1",
            "report_id": self.id,
            "radar": self.radar,
            "period": self.period,
            "kind": self.kind,
            "title": self.title,
            "generated_at": self.generated_at,
            "meta": self.meta,
            "events": [
                {
                    "event_id": e.event_id,
                    "title": e.title,
                    "source": e.source,
                    "source_url": e.source_url,
                    "score": e.score,
                    "tier": e.tier,
                    "tags": e.tags,
                } for e in self.events[:50]
            ],
            "markdown": self.markdown,
        }
