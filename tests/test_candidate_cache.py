from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from radar.schema import Event, EventType, RadarType
from storage.state import StateStore


NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def _event(event_id: str, days_ago: int = 1, **overrides) -> Event:
    data = {
        "event_id": event_id,
        "radar": RadarType.industry,
        "source": "Ethereum Blog",
        "source_url": f"https://example.com/articles/{event_id}",
        "title": f"Release {event_id}",
        "published_at": NOW - timedelta(days=days_ago),
        "excerpt": "A concrete change",
        "event_type": EventType.news,
        "score": 72,
        "tier": "weekly",
    }
    data.update(overrides)
    return Event(**data)


def test_candidate_cache_round_trip_preserves_event_and_omits_raw_meta():
    with tempfile.TemporaryDirectory() as tmp, patch("storage.state._utc_now", return_value=NOW):
        state = StateStore(state_dir=Path(tmp), namespace="test")
        event = _event("e1", developer_action="Read the diff", raw_meta={"private_url": "https://x?token=private"})
        assert state.record_candidates("industry", [event]) == 1

        path = state.dir / "candidates_industry.json"
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        assert payload["schema_version"] == 2
        assert payload["radar"] == "industry"
        assert "raw_meta" not in raw
        assert "private" not in raw
        assert payload["events"][0]["published_at"] == "2026-11-10T12:00:00+00:00"
        loaded = StateStore(state_dir=Path(tmp), namespace="test").load_candidates("industry", 7)
        assert len(loaded) == 1
        assert loaded[0].event_id == "e1"
        assert loaded[0].developer_action == "Read the diff"
        assert loaded[0].raw_meta == {}


def test_candidate_cache_dedupes_by_id_and_isolates_radars():
    with tempfile.TemporaryDirectory() as tmp, patch("storage.state._utc_now", return_value=NOW):
        state = StateStore(state_dir=Path(tmp), namespace="test")
        assert state.record_candidates("industry", [_event("e1", score=60)]) == 1
        assert state.record_candidates("industry", [_event("e1", score=88)]) == 1
        competitor = _event("c1", radar=RadarType.competitor)
        assert state.record_candidates("competitor", [competitor]) == 1
        assert state.record_candidates("industry", [competitor]) == 1
        assert [e.score for e in state.load_candidates("industry", 7)] == [88]
        assert [e.event_id for e in state.load_candidates("competitor", 7)] == ["c1"]


def test_candidate_cache_uses_utc_publication_window_and_excludes_undated_snapshots():
    with tempfile.TemporaryDirectory() as tmp, patch("storage.state._utc_now", return_value=NOW):
        state = StateStore(state_dir=Path(tmp), namespace="test")
        events = [
            _event("recent", 6),
            _event("ten-days", 10),
            _event("boundary", 14),
            _event("expired", 15),
            _event("future", published_at=NOW + timedelta(days=1)),
            _event("undated", published_at=None, event_type=EventType.defi_metric),
            _event("naive-utc", published_at=(NOW - timedelta(days=2)).replace(tzinfo=None)),
            _event("noise", tier="noise"),
        ]
        assert state.record_candidates("industry", events) == 4
        assert {e.event_id for e in state.load_candidates("industry", 7)} == {"recent", "naive-utc"}
        assert {e.event_id for e in state.load_candidates("industry", 14)} == {
            "recent", "naive-utc", "ten-days", "boundary",
        }
        assert len(state.load_candidates("industry", 30)) == 4  # retention cap


def test_candidate_cache_has_bounded_item_count():
    with tempfile.TemporaryDirectory() as tmp, patch("storage.state._utc_now", return_value=NOW), patch(
        "storage.state.CANDIDATE_MAX_ITEMS", 3
    ):
        state = StateStore(state_dir=Path(tmp), namespace="test")
        events = [_event(f"e{i}", days_ago=i) for i in range(5)]
        assert state.record_candidates("industry", events) == 3
        assert [e.event_id for e in state.load_candidates("industry", 14)] == ["e0", "e1", "e2"]


def test_candidate_cache_has_bounded_file_size():
    with tempfile.TemporaryDirectory() as tmp, patch("storage.state._utc_now", return_value=NOW), patch(
        "storage.state.CANDIDATE_MAX_FILE_BYTES", 1600
    ):
        state = StateStore(state_dir=Path(tmp), namespace="test")
        events = [_event(f"e{i}", excerpt="A" * 800) for i in range(5)]
        state.record_candidates("industry", events)
        assert (state.dir / "candidates_industry.json").stat().st_size <= 1600


def test_candidate_cache_never_stores_access_bearing_urls():
    with tempfile.TemporaryDirectory() as tmp, patch("storage.state._utc_now", return_value=NOW):
        state = StateStore(state_dir=Path(tmp), namespace="test")
        events = [
            _event("safe"),
            _event("query", source_url="https://example.com/story?access_token=private"),
            _event("userinfo", source_url="https://user:private@example.com/story"),
            _event("webhook", source_url="https://open.feishu.cn/open-apis/bot/v2/hook/private"),
            _event("excerpt", excerpt="See https://example.com/story?X-Amz-Signature=private"),
            _event("tag", tags=["https://example.com/story#token=private"]),
            _event("nested", source_url="https://example.com/story?redirect=https%3A%2F%2Fuser%3Aprivate%40x.io"),
            _event("scheme", source_url="file:///private/tmp/story"),
            _event("x" * 129),
        ]
        assert state.record_candidates("industry", events) == 1
        raw = (state.dir / "candidates_industry.json").read_text(encoding="utf-8")
        assert "private" not in raw
        assert [e.event_id for e in state.load_candidates("industry", 7)] == ["safe"]


def test_candidate_cache_recovers_corrupt_file_and_rejects_wrong_schema():
    with tempfile.TemporaryDirectory() as tmp, patch("storage.state._utc_now", return_value=NOW):
        state = StateStore(state_dir=Path(tmp), namespace="test")
        path = state.dir / "candidates_industry.json"
        path.write_text("{broken", encoding="utf-8")
        assert state.load_candidates("industry", 7) == []
        assert state.record_candidates("industry", [_event("e1")]) == 1
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = 99
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert state.load_candidates("industry", 7) == []
        assert state.record_candidates("industry", [_event("e2")]) == 1
        assert [e.event_id for e in state.load_candidates("industry", 7)] == ["e2"]


def test_candidate_cache_rejects_invalid_radar_and_lookback():
    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        try:
            state.record_candidates("../other", [_event("e1")])
            assert False, "invalid radar must raise"
        except ValueError:
            pass
        try:
            state.load_candidates("industry", 0)
            assert False, "invalid lookback must raise"
        except ValueError:
            pass
        assert list(state.dir.glob("*.json")) == []
