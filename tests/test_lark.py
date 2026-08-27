from outputs.lark import build_industry_card, build_competitor_card, send_lark

def test_build_cards():
    evs = [{"title":"Test event","url":"https://example.com","score":80}]
    c1 = build_industry_card("Title","summary",evs)
    assert c1["msg_type"]=="interactive"
    assert "Web3 Industry" in c1["card"]["header"]["title"]["content"]
    c2 = build_competitor_card("Title","summary",evs)
    assert "Competitor" in c2["card"]["header"]["title"]["content"]

def test_dry_run():
    payload = build_industry_card("t","s",[])
    res = send_lark("https://example.com", payload, dry_run=True)
    assert res["dry_run"] == True
