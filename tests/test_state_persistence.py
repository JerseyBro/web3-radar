import json
import os
from pathlib import Path
import tempfile

from storage.state import StateStore
from storage import git_state


def _tmp_state():
    return StateStore(state_dir=Path(tempfile.mkdtemp()))


def test_state_survives_second_run():
    d = Path(tempfile.mkdtemp())
    s1 = StateStore(state_dir=d)
    s1.add_seen(["e1", "e2"])
    s1.save_clusters({"c1": ["e1"]})
    s1.record_cost("m", 100, 50, 0.01)
    s1.record_delivery("lark", "k1", "ok")
    # simulate a brand new process reading the same dir
    s2 = StateStore(state_dir=d)
    assert "e1" in s2.load_seen()
    assert s2.load_clusters().get("c1") == ["e1"]
    assert s2.already_delivered("lark", "k1") is True
    assert abs(s2.monthly_cost_usd() - 0.01) < 1e-6


def test_atomic_write_leaves_no_tmp():
    s = _tmp_state()
    s.add_seen(["x"])
    tmp_files = list(s.dir.glob("*.tmp"))
    assert tmp_files == [], f"leftover tmp files: {tmp_files}"
    # file is valid json
    raw = (s.dir / "seen.json").read_text()
    assert "schema_version" in json.loads(raw)


def test_corrupt_file_auto_init():
    s = _tmp_state()
    (s.dir / "cost.json").write_text("{not valid json")
    # should not raise; returns fresh default
    assert s.monthly_cost_usd() == 0.0


def test_git_state_noop_without_token():
    d = Path(tempfile.mkdtemp())
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("GITHUB_REPOSITORY", None)
    assert git_state.pull_state(d) is False
    assert git_state.push_state(d, "test") is False
