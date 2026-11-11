from __future__ import annotations

from datetime import datetime, timezone

from outputs.lark import build_card_from_report, build_industry_card
from radar.report import Report
from radar.schema import Event, RadarType


def _event(index: int, *, url: str | None = None, title: str | None = None) -> Event:
    return Event(
        event_id=f"e-{index}", radar=RadarType.industry, source=f"Official {index}",
        source_url=url or f"https://example.com/story/{index}",
        title=title or f"Protocol update {index}",
        published_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
        excerpt=f"Protocol {index} published a change.",
        why_it_matters="Developers may need to review their integration.",
    )


def _contents(card: dict) -> list[str]:
    return [item["text"]["content"] for item in card["card"]["elements"]]


def test_brief_is_self_contained_and_links_only_three_sources():
    report = Report(
        radar="industry", period="2026-W46", markdown="# Very long Markdown\n" + "UNSAFE_TABLE " * 100,
        events=[_event(i) for i in range(5)],
        meta={"sources_checked": 11, "sources_failed": 2, "analysis_mode": "rules",
              "report_url": "https://github.com/example/radar/actions/runs/123"},
    )
    contents = _contents(build_card_from_report(report))
    rendered = "\n".join(contents)
    assert "来源可用 9/11" in rendered
    assert "入选 5 条" in rendered
    assert "规则筛选" in rendered
    assert "2 个来源失败" in rendered
    assert "可能影响" in rendered
    assert "UNSAFE_TABLE" not in rendered
    assert "story/0" in rendered and "story/2" in rendered
    assert "story/3" not in rendered
    assert "打开运行记录并下载完整报告" in rendered


def test_empty_brief_distinguishes_screening_from_market_claim():
    report = Report(
        radar="competitor", period="2026-W46", events=[],
        meta={"sources_checked": 10, "sources_failed": 3, "analysis_mode": "rules"},
    )
    card = build_card_from_report(report)
    rendered = "\n".join(_contents(card))
    assert "来源可用 7/10" in rendered
    assert "3 个来源失败" in rendered
    assert "无达标新信号" in rendered
    assert "市场没有变化" in rendered  # negated explicitly, not implied
    assert "完整报告" not in rendered
    assert "Competitor" in card["card"]["header"]["title"]["content"]


def test_unsafe_source_url_and_markdown_title_cannot_inject_links():
    report = Report(
        radar="industry", period="2026-W46",
        events=[
            _event(0, url="javascript:alert(1)", title="Bad [link](https://evil.example)"),
            _event(1, title="Update [click](https://evil.example) **now**"),
        ],
        meta={"report_url": "https://github.com/example/radar/actions/runs/1)malicious"},
    )
    rendered = "\n".join(_contents(build_card_from_report(report)))
    assert "javascript:" not in rendered
    assert "Bad" not in rendered
    assert "1 条信号因来源链接未通过校验" in rendered
    assert "[click](https://evil.example)" not in rendered
    assert r"\[click\]" in rendered
    assert "打开运行记录" not in rendered
    assert "https://example.com/story/1" in rendered


def test_legacy_card_entry_point_keeps_shape_without_report_link():
    card = build_industry_card("Title", "One concise sentence.", [
        {"title": "Event", "url": "https://example.com/event", "score": 80},
    ])
    rendered = "\n".join(_contents(card))
    assert card["msg_type"] == "interactive"
    assert "One concise sentence" in rendered
    assert "https://example.com/event" in rendered
    assert "完整报告" not in rendered


def test_archive_only_brief_labels_every_item_as_unverified_candidate():
    report = Report(
        radar="industry", period="2026-W46",
        events=[_event(0), _event(1)],
        meta={"candidate_only": True, "sources_checked": 2, "sources_failed": 0},
    )
    contents = _contents(build_card_from_report(report))
    rendered = "\n".join(contents)
    assert "待验证候选 2 条" in rendered
    assert "入选 2 条" not in rendered
    assert sum("待验证 · " in content for content in contents) == 2
    assert "完整报告" not in rendered
