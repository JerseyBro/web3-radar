from __future__ import annotations
from radar.schema import Event
import yaml
from pathlib import Path

def load_scoring():
    p = Path(__file__).resolve().parent.parent / "config" / "scoring.yaml"
    if p.exists():
        import yaml
        return yaml.safe_load(open(p))
    return {}

def score_industry(event: Event, weights: dict | None = None) -> int:
    w = weights or {"impact":0.25,"wallet_relevance":0.25,"novelty":0.15,"credibility":0.15,"money_flow_significance":0.10,"technical_significance":0.10}
    s = (
        event.impact * w.get("impact",0) +
        event.wallet_relevance * w.get("wallet_relevance",0) +
        event.novelty * w.get("novelty",0) +
        event.credibility * w.get("credibility",0) +
        event.money_flow_significance * w.get("money_flow_significance",0) +
        event.technical_significance * w.get("technical_significance",0)
    )
    return int(round(s))

def score_competitor(event: Event, weights: dict | None = None) -> int:
    w = weights or {"strategic_importance":0.30,"wallet_relevance":0.25,"novelty":0.20,"credibility":0.15,"execution_signal":0.10}
    s = (
        event.strategic_importance * w.get("strategic_importance",0) +
        event.wallet_relevance * w.get("wallet_relevance",0) +
        event.novelty * w.get("novelty",0) +
        event.credibility * w.get("credibility",0) +
        event.execution_signal * w.get("execution_signal",0)
    )
    return int(round(s))

def apply_score(events: list[Event], radar: str, scoring_cfg: dict | None = None) -> list[Event]:
    cfg = scoring_cfg or load_scoring()
    if radar == "industry":
        w = cfg.get("industry",{}).get("weights")
        for e in events:
            e.score = score_industry(e, w)
            e.tier = e.tier_from_score(radar)
    else:
        w = cfg.get("competitor",{}).get("weights")
        for e in events:
            e.score = score_competitor(e, w)
            e.tier = e.tier_from_score(radar)
    return events

def tier_label(score: int) -> str:
    if score >= 90: return "critical"
    if score >= 75: return "important"
    if score >= 60: return "weekly"
    if score >= 40: return "archive"
    return "noise"
