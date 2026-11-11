"""Reports and Lark cards must not expose access-bearing source URLs."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from outputs.local_http import LocalHTTPOutput
from outputs.file import FileOutput
from outputs.base import DeliveryContext
from outputs.lark import build_card_from_report
from pipeline.analyze import build_classifier_prompt
from radar.report import Report, build_solo_report, public_source_url
from radar.schema import Event, EventType, RadarType
from storage.store import append_events


def test_sensitive_source_url_not_exported_or_linked():
    secret_url = "https://example.org/article?access_token=DO_NOT_EXPORT"
    event = Event(event_id="e", radar=RadarType.industry, source="source",
                  source_url=secret_url, title="Update", tier="weekly")
    report = Report(radar="industry", period="2026-W46", events=[event])
    serialized = json.dumps(report.canonical_json())
    card = json.dumps(build_card_from_report(report))
    assert "DO_NOT_EXPORT" not in serialized
    assert "DO_NOT_EXPORT" not in card
    assert report.canonical_json()["events"][0]["source_url"] == ""


def test_normal_source_url_kept():
    url = "https://example.org/article?lang=zh"
    event = Event(event_id="e", radar=RadarType.industry, source="source",
                  source_url=url, title="Update", tier="weekly")
    report = Report(radar="industry", period="2026-W46", events=[event])
    assert report.canonical_json()["events"][0]["source_url"] == url
    assert url in json.dumps(build_card_from_report(report))


def test_signed_url_variants_are_blocked():
    for query in ("X-Amz-Signature=DO_NOT_EXPORT", "auth_token=DO_NOT_EXPORT", "apiKey=DO_NOT_EXPORT"):
        assert public_source_url(f"https://example.org/article?{query}") is None
    assert public_source_url("https://open.feishu.cn/open-apis/bot/v2/hook/DO_NOT_EXPORT") is None


def test_signed_url_not_sent_to_local_http_or_llm_or_event_log():
    secret_url = "https://example.org/article?X-Amz-Signature=DO_NOT_EXPORT"
    event = Event(event_id="e", radar=RadarType.industry, source="source",
                  source_url=secret_url, title="Update", tier="weekly")
    report = Report(radar="industry", period="2026-W46", events=[event])
    payload = LocalHTTPOutput()._envelope(report, None)
    _, user_prompt = build_classifier_prompt([event], "industry")
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        with patch("storage.store.events_path", return_value=path):
            append_events([event])
        stored = path.read_text(encoding="utf-8")
    assert "DO_NOT_EXPORT" not in json.dumps(payload)
    assert "DO_NOT_EXPORT" not in user_prompt
    assert "DO_NOT_EXPORT" not in stored


def test_api_announcement_gets_reproducible_builder_action():
    event = Event(event_id="api", radar=RadarType.competitor, source="Zerion Blog",
                  source_url="https://example.org/api", title="Build with Example API",
                  event_type=EventType.blog_post, tier="archive")
    report = build_solo_report("competitor", "2026-W46", [event], candidate_only=True)
    assert "只读最小请求" in report
    assert "待验证候选" in report
    card = json.dumps(build_card_from_report(Report(radar="competitor", period="2026-W46", events=[event])), ensure_ascii=False)
    assert "下一步验证" in card


def test_access_bearing_url_embedded_in_title_is_redacted_everywhere():
    title = "Update https://example.org/private?auth_token=DO_NOT_EXPORT"
    event = Event(event_id="embedded", radar=RadarType.industry, source="source",
                  source_url="https://example.org/public", title=title, tier="weekly")
    report = Report(radar="industry", period="2026-W46", events=[event],
                    markdown=build_solo_report("industry", "2026-W46", [event]))
    _, user_prompt = build_classifier_prompt([event], "industry")
    assert "DO_NOT_EXPORT" not in json.dumps(report.canonical_json())
    assert "DO_NOT_EXPORT" not in json.dumps(build_card_from_report(report))
    assert "DO_NOT_EXPORT" not in user_prompt


def test_markdown_file_output_redacts_embedded_access_link():
    report = Report(radar="industry", period="2026-W46",
                    markdown="see https://example.org/private?auth_token=DO_NOT_EXPORT")
    with TemporaryDirectory() as tmp:
        output = FileOutput(reports_dir=Path(tmp))
        output.deliver(report, DeliveryContext(radar="industry", report_id=report.id, title=report.title))
        md = (Path(tmp) / "2026-W46-industry.md").read_text(encoding="utf-8")
    assert "DO_NOT_EXPORT" not in md
    assert "DO_NOT_EXPORT" not in json.dumps(report.canonical_json())
