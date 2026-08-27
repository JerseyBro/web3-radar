from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
STATE_SCHEMA_VERSION = 1

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _month_key(dt: datetime | None = None) -> str:
    dt = dt or _now()
    return dt.strftime("%Y-%m")

def atomic_write(path: Path, obj: dict):
    """Write JSON atomically: tmp file + rename. Never leave a half-written state."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(obj, indent=2, ensure_ascii=False)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def _load_or_init(path: Path, default: dict) -> dict:
    path = Path(path)
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != STATE_SCHEMA_VERSION:
            # attempt migration / reinit
            return default
        return data
    except Exception:
        return default

# ---------- seen / clusters ----------
def seen_path() -> Path:
    return ROOT / "storage" / "state" / "seen.json"

def load_seen() -> set:
    d = _load_or_init(seen_path(), {"schema_version": STATE_SCHEMA_VERSION, "ids": []})
    return set(d.get("ids", []))

def save_seen(ids: set[str]):
    atomic_write(seen_path(), {"schema_version": STATE_SCHEMA_VERSION, "ids": sorted(list(ids))})

def clusters_path() -> Path:
    return ROOT / "storage" / "state" / "clusters.json"

def save_clusters(mapping: dict):
    atomic_write(clusters_path(), {"schema_version": STATE_SCHEMA_VERSION, "clusters": mapping})

def load_clusters() -> dict:
    d = _load_or_init(clusters_path(), {"schema_version": STATE_SCHEMA_VERSION, "clusters": {}})
    return d.get("clusters", {})

# ---------- critical alerts ----------
def critical_alerts_path() -> Path:
    return ROOT / "storage" / "state" / "critical_alerts.json"

def load_critical_alerts() -> set:
    d = _load_or_init(critical_alerts_path(), {"schema_version": STATE_SCHEMA_VERSION, "ids": []})
    return set(d.get("ids", []))

def save_critical_alerts(ids: set[str]):
    atomic_write(critical_alerts_path(), {"schema_version": STATE_SCHEMA_VERSION, "ids": sorted(list(ids))})

def is_new_critical(event_id: str) -> bool:
    return event_id not in load_critical_alerts()

def mark_critical_alerted(event_id: str):
    s = load_critical_alerts()
    s.add(event_id)
    save_critical_alerts(s)

# ---------- resolved sources ----------
def resolved_sources_path() -> Path:
    return ROOT / "storage" / "state" / "resolved_sources.json"

def load_resolved_sources() -> dict:
    d = _load_or_init(resolved_sources_path(), {"schema_version": STATE_SCHEMA_VERSION, "wallets": {}})
    return d.get("wallets", {})

def save_resolved_sources(data: dict):
    atomic_write(resolved_sources_path(), {"schema_version": STATE_SCHEMA_VERSION, "wallets": data})

# ---------- monthly cost ----------
def cost_path() -> Path:
    return ROOT / "storage" / "state" / "cost.json"

def _init_cost(month: str) -> dict:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "month": month,
        "estimated_cost_usd": 0.0,
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }

def load_cost() -> dict:
    now_month = _month_key()
    d = _load_or_init(cost_path(), _init_cost(now_month))
    if d.get("month") != now_month:
        # rollover: start fresh month, preserve nothing (monthly budget)
        d = _init_cost(now_month)
        atomic_write(cost_path(), d)
    return d

def add_cost(model: str, input_tokens: int, output_tokens: int, cost: float):
    d = load_cost()
    d["calls"] += 1
    d["input_tokens"] += input_tokens
    d["output_tokens"] += output_tokens
    d["estimated_cost_usd"] = round(d["estimated_cost_usd"] + cost, 6)
    atomic_write(cost_path(), d)
    return d

# ---------- delivery idempotency ----------
def delivery_path() -> Path:
    return ROOT / "storage" / "state" / "delivery.json"

def _init_delivery() -> dict:
    return {"schema_version": STATE_SCHEMA_VERSION, "deliveries": {}}

def load_delivery() -> dict:
    d = _load_or_init(delivery_path(), _init_delivery())
    return d

def delivery_key(target: str, report_id: str) -> str:
    return f"{target}:{report_id}"

def was_delivered(target: str, report_id: str) -> bool:
    d = load_delivery()
    return delivery_key(target, report_id) in d.get("deliveries", {})

def mark_delivered(target: str, report_id: str, status: str):
    d = load_delivery()
    d.setdefault("deliveries", {})[delivery_key(target, report_id)] = {
        "delivered_at": _now().isoformat(),
        "status": status,
    }
    atomic_write(delivery_path(), d)

# ---------- events / reports ----------
def events_path(dt: datetime | None = None) -> Path:
    dt = dt or _now()
    return ROOT / "storage" / "events" / f"{dt.strftime('%Y-%m')}.jsonl"

def append_events(events: list):
    p = events_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for e in events:
            f.write(e.model_dump_json() + "\n")

def load_recent_events(days: int = 7) -> list:
    from radar.schema import Event
    events = []
    for p in sorted((ROOT / "storage" / "events").glob("*.jsonl"))[-2:]:
        try:
            for line in open(p, encoding="utf-8"):
                if line.strip():
                    events.append(Event.model_validate_json(line))
        except: pass
    return events

def report_path(radar: str, dt: datetime | None = None) -> Path:
    dt = dt or _now()
    year, week, _ = dt.isocalendar()
    return ROOT / "reports" / f"{year}-W{week:02d}-{radar}.md"

def report_json_path(radar: str, dt: datetime | None = None) -> Path:
    dt = dt or _now()
    year, week, _ = dt.isocalendar()
    return ROOT / "reports" / f"{year}-W{week:02d}-{radar}.json"

def local_receiver_dir() -> Path:
    return ROOT / "storage" / "local-receiver"

def rotate_events(keep_months: int = 6):
    import time
    now = time.time()
    for p in (ROOT / "storage" / "events").glob("*.jsonl"):
        if now - p.stat().st_mtime > keep_months*30*24*3600:
            try: p.unlink()
            except: pass

def make_report_id(radar: str, period: str, report_type: str = "weekly") -> str:
    import hashlib
    return hashlib.sha256(f"{radar}|{period}|{report_type}".encode()).hexdigest()[:16]
