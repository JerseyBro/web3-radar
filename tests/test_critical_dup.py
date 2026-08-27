from pathlib import Path
import tempfile, json
from storage.store import load_critical_alerts, save_critical_alerts, is_new_critical, mark_critical_alerted

def _patch(d):
    import storage.store as st
    st.critical_alerts_path = lambda: Path(d)/"critical.json"

def test_critical_dup_protection():
    with tempfile.TemporaryDirectory() as d:
        import storage.store as st
        orig = st.critical_alerts_path
        _patch(d)
        try:
            save_critical_alerts({"abc123"})
            assert "abc123" in load_critical_alerts()
            save_critical_alerts({"abc123","def456"})
            assert load_critical_alerts() == {"abc123","def456"}
            s = load_critical_alerts()
            assert "abc123" in s
        finally:
            st.critical_alerts_path = orig

def test_critical_no_repeat_alert():
    """Same event_id must not be alerted twice."""
    with tempfile.TemporaryDirectory() as d:
        import storage.store as st
        orig = st.critical_alerts_path
        _patch(d)
        try:
            assert is_new_critical("evt-1") is True
            mark_critical_alerted("evt-1")
            assert is_new_critical("evt-1") is False
            # a different event is still new
            assert is_new_critical("evt-2") is True
        finally:
            st.critical_alerts_path = orig

