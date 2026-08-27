from radar.schema import Event, RadarType
from pipeline.dedupe import exact_dedupe, fuzzy_dedupe, dedupe
from tests._util import skip, module_available

HAS_RAPIDFUZZ = module_available("rapidfuzz")

def mk(title, url):
    return Event(event_id=Event.make_id(url, title), radar=RadarType.industry, source="test", source_url=url, title=title, excerpt="")

def test_exact_dedupe():
    e1 = mk("Hello World", "https://example.com/a?utm_source=x")
    e2 = mk("Hello World", "https://example.com/a")
    res, cnt = exact_dedupe([e1,e2])
    assert len(res)==1 and cnt==1
    assert res[0].source_url == "https://example.com/a"

def test_fuzzy_dedupe():
    if not HAS_RAPIDFUZZ:
        skip("rapidfuzz not installed (optional dep)")
    e1 = mk("Bitget Wallet v2.3.1 Update", "https://example.com/1")
    e2 = mk("Bitget Wallet v2.3.1 update", "https://example.com/2")
    res, cnt = fuzzy_dedupe([e1,e2], threshold=88)
    assert cnt==1

def test_dedupe_combined():
    e1 = mk("Solana TVL hits $10B", "https://example.com/1")
    e2 = mk("Solana TVL hits $10B", "https://example.com/1")
    e3 = mk("Solana TVL hits $10b", "https://example.com/2")
    res, stats = dedupe([e1,e2,e3], fuzzy_threshold=88)
    assert stats["total_removed"]>=1
