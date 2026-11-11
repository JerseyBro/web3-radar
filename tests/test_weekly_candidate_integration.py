"""A scheduled scan can contribute a dated event to a later weekly runner."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from radar.cli import run_radar
from radar.report import build_solo_report
from radar.schema import Event, RadarType
from storage.state import StateStore


def _event() -> Event:
    return Event(event_id="within-week", radar=RadarType.industry, source="official",
                 source_url="https://example.org/announcement", title="Developer API released",
                 published_at=datetime.now(timezone.utc), score=75, tier="important")


def _result(events: list[Event]) -> dict:
    return {
        "events": events, "processed_ids": [event.event_id for event in events],
        "critical_events": [], "sources_checked": 1, "sources_failed": 0,
        "candidate_events": len(events), "high_signal": len(events),
    }


def test_weekly_merges_earlier_scan_candidate_across_state_store_instances():
    async def fake_scan(http, settings, guard, client, *, do_ai, seen, weekly):
        return _result([] if weekly else [_event()])

    with TemporaryDirectory() as tmp:
        with patch("radars.industry.run_industry_scan", side_effect=fake_scan):
            scan_state = StateStore(state_dir=Path(tmp), namespace="test")
            asyncio.run(run_radar("industry", {}, scan_state, None, None, None,
                                  do_ai=False, weekly=False, record_seen=True))
            assert "within-week" in scan_state.load_seen()
            weekly_state = StateStore(state_dir=Path(tmp), namespace="test")
            weekly = asyncio.run(run_radar("industry", {"runtime": {"pipeline": {"weekly_lookback_days": 7}}},
                                           weekly_state, None, None, None,
                                           do_ai=False, weekly=True, record_seen=True))
    assert [event.event_id for event in weekly["events"]] == ["within-week"]
    assert weekly["cached_events_added"] == 1
    assert "此前扫描" in build_solo_report("industry", "2026-W46", weekly["events"], cached_count=1)


def test_dry_run_scan_does_not_persist_candidate_cache():
    async def fake_scan(http, settings, guard, client, *, do_ai, seen, weekly):
        return _result([_event()])

    with TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        with patch("radars.industry.run_industry_scan", side_effect=fake_scan):
            asyncio.run(run_radar("industry", {}, state, None, None, None,
                                  do_ai=False, weekly=False, record_seen=False))
        assert state.load_candidates("industry", 7) == []
