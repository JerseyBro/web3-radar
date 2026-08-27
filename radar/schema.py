from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RadarType(str, Enum):
    industry = "industry"
    competitor = "competitor"


class EventType(str, Enum):
    news = "news"
    app_update = "app_update"
    github_release = "github_release"
    blog_post = "blog_post"
    docs_update = "docs_update"
    defi_metric = "defi_metric"
    market_data = "market_data"
    unknown = "unknown"


class Event(BaseModel):
    event_id: str = Field(description="Deterministic hash id")
    radar: RadarType
    entity: Optional[str] = None  # e.g. wallet name or chain
    source: str
    source_url: str
    title: str
    published_at: Optional[datetime] = None
    excerpt: str = ""
    event_type: EventType = EventType.unknown
    tags: list[str] = Field(default_factory=list)

    # Scoring dimensions 0-100
    credibility: int = 50
    novelty: int = 50
    impact: int = 50
    wallet_relevance: int = 50
    technical_significance: int = 50
    money_flow_significance: int = 50
    # competitor specific
    strategic_importance: int = 50
    execution_signal: int = 50

    score: int = 0
    tier: str = "noise"

    cluster_id: Optional[str] = None
    duplicate_of: Optional[str] = None

    ai_summary: Optional[str] = None
    why_it_matters: Optional[str] = None
    wallet_implication: Optional[str] = None

    raw_meta: dict = Field(default_factory=dict)

    @staticmethod
    def make_id(source_url: str, title: str) -> str:
        h = hashlib.sha256(f"{source_url}|{title}".encode()).hexdigest()[:16]
        return h

    def tier_from_score(self, radar: str = "industry") -> str:
        s = self.score
        if s >= 90:
            return "critical"
        if s >= 75:
            return "important"
        if s >= 60:
            return "weekly"
        if s >= 40:
            return "archive"
        return "noise"
