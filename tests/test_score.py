from radar.schema import Event, RadarType
from pipeline.score import score_industry, score_competitor, tier_label

def test_industry_score():
    e = Event(event_id="1", radar=RadarType.industry, source="s", source_url="https://x", title="t", impact=80, wallet_relevance=80, novelty=60, credibility=80, money_flow_significance=70, technical_significance=50)
    s = score_industry(e)
    assert 60 <= s <= 90

def test_competitor_score():
    e = Event(event_id="1", radar=RadarType.competitor, source="s", source_url="https://x", title="t", strategic_importance=90, wallet_relevance=80, novelty=70, credibility=80, execution_signal=60)
    s = score_competitor(e)
    assert s >= 75

def test_tier():
    assert tier_label(95)=="critical"
    assert tier_label(80)=="important"
    assert tier_label(65)=="weekly"
    assert tier_label(45)=="archive"
    assert tier_label(10)=="noise"
