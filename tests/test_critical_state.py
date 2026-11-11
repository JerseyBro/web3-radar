from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from storage.state import StateStore


def test_critical_alerts_are_isolated_by_namespace():
    with tempfile.TemporaryDirectory() as tmp, patch("storage.state.STATE_DIR", Path(tmp)):
        production = StateStore(namespace="production")
        acceptance = StateStore(namespace="acceptance")
        test = StateStore(namespace="test")

        assert production.is_new_critical("event-1")
        assert acceptance.is_new_critical("event-1")
        production.mark_critical_alerted("event-1")
        assert not production.is_new_critical("event-1")
        assert acceptance.is_new_critical("event-1")
        assert test.is_new_critical("event-1")

        acceptance.mark_critical_alerted("event-2")
        test.mark_critical_alerted("event-3")
        assert production.is_new_critical("event-2")
        assert production.is_new_critical("event-3")
        assert not StateStore(namespace="acceptance").is_new_critical("event-2")
        assert not StateStore(namespace="test").is_new_critical("event-3")
        assert (Path(tmp) / "critical_alerts.json").is_file()
        assert (Path(tmp) / "acceptance" / "critical_alerts.json").is_file()
        assert (Path(tmp) / "test" / "critical_alerts.json").is_file()


def test_critical_alerts_migrate_legacy_schema_and_bare_lists():
    legacy_payloads = [
        {"schema_version": 1, "ids": ["old-1", "old-2"]},
        {"ids": ["old-1", "old-2"]},
        ["old-1", "old-2"],
    ]
    for legacy in legacy_payloads:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "critical_alerts.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            state = StateStore(state_dir=Path(tmp), namespace="test")
            assert not state.is_new_critical("old-1")
            assert state.is_new_critical("new")
            state.mark_critical_alerted("new")
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data == {"schema_version": 2, "ids": ["new", "old-1", "old-2"]}
            state.mark_critical_alerted("new")
            assert json.loads(path.read_text(encoding="utf-8")) == data


def test_critical_alerts_recover_corrupt_file_without_touching_other_state():
    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        path = Path(tmp) / "critical_alerts.json"
        path.write_text("not-json", encoding="utf-8")
        assert state.is_new_critical("event-1")
        state.mark_critical_alerted("event-1")
        assert not state.is_new_critical("event-1")
        assert list(Path(tmp).glob("*.tmp")) == []
