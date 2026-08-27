from radar.schema import Event, RadarType
from pipeline.normalize import canonicalize_url
from pipeline.filter import filter_events
from pipeline.dedupe import dedupe
from pipeline.cluster import cluster_events
from pipeline.score import apply_score
from radar.cli import build_fallback_report
from outputs.lark import build_industry_card, send_lark

def _mk(title, url, radar="industry", **kw):
    e = Event(event_id=Event.make_id(url, title), radar=RadarType(radar), source="test", source_url=url, title=title)
    for k,v in kw.items():
        setattr(e,k,v)
    return e

def test_e2e_offline_pipeline():
    evs = [
        _mk("Solana TVL hits $12B as stablecoin inflows surge", "https://defillama.com/chain/Solana", money_flow_significance=85, impact=80, wallet_relevance=70, novelty=60, credibility=90),
        _mk("Solana TVL hits $12b as stablecoin inflows surge", "https://defillama.com/chain/Solana", money_flow_significance=85, impact=80, wallet_relevance=70, novelty=60, credibility=90),
        _mk("Bug fixes and performance improvements", "https://example.com/bf", radar="competitor", strategic_importance=10, wallet_relevance=10),
    ]
    kept, noise = filter_events(evs)
    assert len(noise) == 1  # bug fixes removed
    deduped, stats = dedupe(kept)
    assert stats["total_removed"] >= 1  # duplicate removed
    clustered = cluster_events(deduped)
    scored = apply_score(clustered, "industry")
    top = [e for e in scored if e.score >= 60]
    assert len(top) >= 1
    report = build_fallback_report("industry", top)
    assert "Solana" in report
    payload = build_industry_card("Weekly", report[:200], [{"title":"Solana","url":"https://x","score":80}])
    assert payload["msg_type"] == "interactive"
    # dry run lark should not send
    res = send_lark("https://example.com", payload, dry_run=True)
    assert res["dry_run"] is True
