from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from radar.schema import Event

ROOT = Path(__file__).resolve().parent.parent

def events_path(dt: datetime | None = None) -> Path:
    dt = dt or datetime.now(timezone.utc)
    return ROOT / "storage" / "events" / f"{dt.strftime('%Y-%m')}.jsonl"

def append_events(events: list[Event]):
    p = events_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for e in events:
            f.write(e.model_dump_json() + "\n")

def load_recent_events(days: int = 7) -> list[Event]:
    # load last 2 months
    events = []
    for p in sorted((ROOT / "storage" / "events").glob("*.jsonl"))[-2:]:
        try:
            for line in open(p, encoding="utf-8"):
                if line.strip():
                    events.append(Event.model_validate_json(line))
        except: pass
    return events

# State helpers
def seen_path() -> Path:
    return ROOT / "storage" / "state" / "seen.json"

def load_seen() -> set[str]:
    p = seen_path()
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text()))
    except: return set()

def save_seen(ids: set[str]):
    p = seen_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(list(ids)), indent=2))

def clusters_path() -> Path:
    return ROOT / "storage" / "state" / "clusters.json"

def save_clusters(mapping: dict):
    p = clusters_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mapping, indent=2, ensure_ascii=False))

def critical_alerts_path() -> Path:
    return ROOT / "storage" / "state" / "critical_alerts.json"

def load_critical_alerts() -> set[str]:
    p = critical_alerts_path()
    if not p.exists(): return set()
    try: return set(json.loads(p.read_text()))
    except: return set()

def save_critical_alerts(ids: set[str]):
    p = critical_alerts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(list(ids)), indent=2))

def is_new_critical(event_id: str) -> bool:
    """Return True only if event_id has not been alerted before."""
    return event_id not in load_critical_alerts()

def mark_critical_alerted(event_id: str):
    s = load_critical_alerts()
    s.add(event_id)
    save_critical_alerts(s)

def rotate_events(keep_months: int = 6):
    import time
    now = time.time()
    for p in (ROOT / "storage" / "events").glob("*.jsonl"):
        if now - p.stat().st_mtime > keep_months*30*24*3600:
            try: p.unlink()
            except: pass

def report_path(radar: str, dt: datetime | None = None) -> Path:
    dt = dt or datetime.now(timezone.utc)
    # ISO week
    year, week, _ = dt.isocalendar()
    return ROOT / "reports" / f"{year}-W{week:02d}-{radar}.md"
