from __future__ import annotations

from datetime import datetime, timezone

from radar.report import Report, build_solo_report
from radar.schema import Event, EventType, RadarType


def _event(**overrides) -> Event:
    data = {
        "event_id": "signal-1",
        "radar": RadarType.industry,
        "source": "DeFiLlama",
        "source_url": "https://defillama.com/chain/Base",
        "title": "Base TVL changed",
        "published_at": datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc),
        "excerpt": "Snapshot",
        "event_type": EventType.defi_metric,
        "score": 67,
        "tier": "weekly",
    }
    data.update(overrides)
    return Event(**data)


def test_solo_report_explains_coverage_source_and_verification():
    event = _event()
    first = build_solo_report("industry", "2026-W46", [event], sources_checked=11, sources_failed=2)
    second = build_solo_report("industry", "2026-W46", [event], sources_checked=11, sources_failed=2)

    assert first == second
    assert "来源成功 9/11" in first
    assert "https://defillama.com/chain/Base" in first
    assert "发布时间：2026-11-10T09:00:00+00:00" in first
    assert "来源记录：DeFiLlama · defi_metric · Snapshot" in first
    assert "产品 / 技术机会假设" in first
    assert "核对指标口径、时间窗口和历史基线" in first
    assert "直接推断资金流向" in first
    assert "尚未独立核实" in first


def test_solo_report_marks_archive_and_ai_action_as_unverified():
    event = _event(tier="archive", score=55, published_at=None)
    event.developer_action = "Check adoption metrics"  # type: ignore[attr-defined]
    report = build_solo_report("competitor", "2026-W46", [event], candidate_only=True)
    assert "待验证候选" in report
    assert "发布时间：未提供" in report
    assert "AI 建议验证动作（待核查）：Check adoption metrics" in report
    assert "本轮入选" not in report


def test_solo_report_empty_reason_does_not_claim_no_activity():
    report = build_solo_report("industry", "2026-W46", [], sources_checked=7, sources_failed=2, empty_reason="EMPTY_BY_SEEN")
    assert "此前处理过的事件可能已被去重" in report
    assert "不证明观察期内没有重要变化" in report
    assert "可能遗漏变化" in report


def test_solo_report_keeps_untrusted_title_literal_and_rejects_non_web_link():
    event = _event(
        title="Risky\n# click [here](javascript:alert(1)) <script>alert(1)</script>",
        excerpt="Injected\n## [read](https://evil.example)",
        source_url="javascript:alert(1)",
        developer_action="Check <img src=x> [link](https://evil.example)",
    )
    report = build_solo_report("industry", "2026-W46", [event])
    assert "\n# click" not in report
    assert "\\[here\\]" in report
    assert "<script>" not in report
    assert "\n## [read]" not in report
    assert "&lt;img src=x&gt;" in report
    assert "来源链接不可用" in report


def test_solo_report_encodes_markdown_in_web_url_and_rejects_credentials():
    event = _event(source_url="https://example.com/[fake](https://evil.example)")
    report = build_solo_report("industry", "2026-W46", [event])
    assert "[fake](https://evil.example)" not in report
    assert "<https://example.com/%5Bfake%5D%28https://evil.example%29>" in report

    event.source_url = "https://example.com/story?access_token=private"
    report = build_solo_report("industry", "2026-W46", [event])
    assert "private" not in report
    assert "来源链接不可用" in report


def test_canonical_report_keeps_v1_fields_and_adds_evidence_fields():
    event = _event()
    payload = Report(radar="industry", period="2026-W46", events=[event]).canonical_json()
    assert payload["schema_version"] == "1"
    assert payload["events"][0]["source_url"] == event.source_url
    assert payload["events"][0]["event_type"] == "defi_metric"
    assert payload["events"][0]["published_at"] == event.published_at.isoformat()
    assert payload["events"][0]["excerpt"] == "Snapshot"
