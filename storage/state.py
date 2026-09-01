from __future__ import annotations
import json
import os
import time
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "storage" / "state"
SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1

# Files persisted on radar-state branch
SEEN = "seen.json"
CLUSTERS = "clusters.json"
COST = "cost.json"
DELIVERIES = "deliveries.json"
RESOLVED = "resolved_sources.json"

# TTL defaults (overridden by config/settings.yaml state.seen_ttl_days)
DEFAULT_SEEN_TTL_DAYS = 14
# Migration timestamp for legacy IDs: set to epoch so they are expired immediately.
# This allows production to recover from starvation (polluted seen) via TTL prune,
# not via manual rm. Window filter will still exclude 2024/2025 old events.
LEGACY_EXPIRED_AT = "2000-01-01T00:00:00+00:00"


def _atomic_write(path: Path, data: Any):
    """Write JSON atomically: write to .tmp then rename. Never corrupt the live file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _now_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _resolve_state_dir(namespace: str, base_dir: Path | None = None) -> Path:
    """Namespace isolation:
    - production -> flat storage/state/ (legacy compat, synced to radar-state branch)
    - acceptance/test -> storage/state/<namespace>/ (isolated, not synced)
    """
    base = base_dir or STATE_DIR
    if namespace == "production":
        return base
    return base / namespace


def _load_ttl_days() -> int:
    # Try config/settings.yaml, fallback to default
    try:
        import yaml  # type: ignore

        p = ROOT / "config" / "settings.yaml"
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            ttl = (data.get("state") or {}).get("seen_ttl_days")
            if isinstance(ttl, int) and ttl > 0:
                return ttl
    except Exception:
        pass
    return DEFAULT_SEEN_TTL_DAYS


class StateStore:
    """Cross-run persistent state. Files are synced to the radar-state git branch by git_state.py (production only)."""

    def __init__(self, state_dir: Path | None = None, namespace: str | None = None, ttl_days: int | None = None):
        # Namespace from env or explicit, default production
        ns = namespace or os.getenv("RADAR_STATE_NAMESPACE") or "production"
        # Allow explicit state_dir to override (tests)
        if state_dir is not None:
            self.dir = Path(state_dir)
            self.namespace = ns
        else:
            self.namespace = ns
            self.dir = _resolve_state_dir(ns)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._ttl_days = ttl_days if ttl_days is not None else _load_ttl_days()

    # ---- low level loaders (auto-init on missing/corrupt) ----
    def _load(self, name: str, default):
        p = self.dir / name
        if not p.exists():
            return default
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "schema_version" in data:
                return data
            # legacy format without schema_version -> wrap
            return {"schema_version": LEGACY_SCHEMA_VERSION, "data": data}
        except Exception:
            # corrupt file -> auto reinit, do not crash pipeline
            return {"schema_version": SCHEMA_VERSION}

    def _save(self, name: str, data: dict):
        # Ensure schema_version is set by caller; if missing, set to current
        if "schema_version" not in data:
            data["schema_version"] = SCHEMA_VERSION
        _atomic_write(self.dir / name, data)

    # ---- seen (cross-run event dedupe with TTL) ----
    def _load_seen_raw(self) -> dict:
        # Default for missing file: new schema empty
        return self._load(SEEN, {"schema_version": SCHEMA_VERSION, "items": {}})

    def _migrate_legacy_seen(self, data: dict) -> tuple[dict, bool]:
        """Migrate legacy schema (ids list) to timestamped items.
        Returns (migrated_data, did_migrate).
        Legacy IDs are assigned LEGACY_EXPIRED_AT so they are pruned immediately,
        allowing production to recover from polluted seen without manual rm.
        Idempotent: if already schema_version 2 with items, no migration.
        """
        # Already new schema with items
        if data.get("schema_version") == SCHEMA_VERSION and "items" in data:
            return data, False
        # Legacy: has ids list (schema 1) or bare list
        ids: list[str] = []
        if "ids" in data and isinstance(data["ids"], list):
            ids = data["ids"]
        elif "data" in data and isinstance(data["data"], list):
            ids = data["data"]
        elif isinstance(data, list):
            ids = data
        # If no ids and not new schema, treat as empty
        if not ids and "items" not in data:
            # Already empty new schema
            if data.get("schema_version") == SCHEMA_VERSION:
                return data, False
            # Legacy empty -> migrate to empty new
            return {"schema_version": SCHEMA_VERSION, "items": {}}, True
        # Migrate: assign expired timestamp so TTL prune clears them
        items = {str(eid): LEGACY_EXPIRED_AT for eid in ids}
        migrated = {"schema_version": SCHEMA_VERSION, "items": items, "migrated_at": _now_iso(), "legacy_count": len(ids)}
        return migrated, True

    def _prune_expired_seen(self, data: dict, now: datetime | None = None) -> tuple[dict, int]:
        """Remove items older than TTL. Returns (pruned_data, removed_count)."""
        if now is None:
            now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=self._ttl_days)
        items = data.get("items") or {}
        if not isinstance(items, dict):
            return data, 0
        kept: dict[str, str] = {}
        removed = 0
        for eid, ts_str in items.items():
            dt = _parse_iso(str(ts_str))
            if dt is None:
                # Corrupt timestamp -> keep? treat as expired to be safe
                removed += 1
                continue
            if dt < cutoff:
                removed += 1
            else:
                kept[eid] = ts_str
        if removed:
            data = dict(data)
            data["items"] = kept
            data["pruned_at"] = _now_iso()
        return data, removed

    def load_seen(self) -> set[str]:
        data = self._load_seen_raw()
        # Migrate if needed
        data, did_migrate = self._migrate_legacy_seen(data)
        if did_migrate:
            # Save migrated file (idempotent)
            self._save(SEEN, data)
        # Prune expired
        data, removed = self._prune_expired_seen(data)
        if removed:
            self._save(SEEN, data)
        items = data.get("items") or {}
        if isinstance(items, dict):
            return set(str(k) for k in items.keys())
        # Fallback legacy
        if "ids" in data and isinstance(data["ids"], list):
            return set(str(x) for x in data["ids"])
        return set()

    def add_seen(self, ids: list[str]):
        if not ids:
            return
        data = self._load_seen_raw()
        # Ensure migrated
        data, did_migrate = self._migrate_legacy_seen(data)
        # Prune before adding
        data, _ = self._prune_expired_seen(data)
        items = data.get("items")
        if not isinstance(items, dict):
            items = {}
            data["items"] = items
        now_iso = _now_iso()
        for eid in ids:
            items[str(eid)] = now_iso
        # cap to avoid unbounded growth (keep most recent 20000 by timestamp)
        if len(items) > 20000:
            # Sort by timestamp desc, keep newest 20000
            sorted_items = sorted(items.items(), key=lambda kv: kv[1], reverse=True)[:20000]
            data["items"] = dict(sorted_items)
        data["schema_version"] = SCHEMA_VERSION
        self._save(SEEN, data)

    # ---- clusters ----
    def load_clusters(self) -> dict:
        d = self._load(CLUSTERS, {"schema_version": SCHEMA_VERSION, "clusters": {}})
        return d.get("clusters", {})

    def save_clusters(self, clusters: dict):
        self._save(CLUSTERS, {"schema_version": SCHEMA_VERSION, "clusters": clusters})

    # ---- cost (true monthly, with rollover) ----
    def load_cost(self) -> dict:
        month = _now_month()
        d = self._load(COST, {"schema_version": SCHEMA_VERSION, "month": month})
        if d.get("month") != month:
            # rollover into new month
            d = {"schema_version": SCHEMA_VERSION, "month": month, "estimated_cost_usd": 0.0,
                 "calls": 0, "input_tokens": 0, "output_tokens": 0}
        return d

    def record_cost(self, model: str, input_tokens: int, output_tokens: int, cost_usd: float):
        d = self.load_cost()
        d["estimated_cost_usd"] = round(d.get("estimated_cost_usd", 0.0) + cost_usd, 6)
        d["calls"] = d.get("calls", 0) + 1
        d["input_tokens"] = d.get("input_tokens", 0) + input_tokens
        d["output_tokens"] = d.get("output_tokens", 0) + output_tokens
        d["last_model"] = model
        self._save(COST, d)
        return d

    def monthly_cost_usd(self) -> float:
        return float(self.load_cost().get("estimated_cost_usd", 0.0))

    # ---- deliveries (idempotency) ----
    def load_deliveries(self) -> list[dict]:
        d = self._load(DELIVERIES, {"schema_version": SCHEMA_VERSION, "deliveries": []})
        return d.get("deliveries", [])

    def already_delivered(self, target: str, key: str) -> bool:
        for x in self.load_deliveries():
            if x.get("target") == target and x.get("key") == key:
                return True
        return False

    def record_delivery(self, target: str, key: str, status: str):
        lst = self.load_deliveries()
        lst.append({
            "target": target, "key": key, "status": status,
            "delivered_at": datetime.now(timezone.utc).isoformat(),
        })
        # keep last 1000
        lst = lst[-1000:]
        self._save(DELIVERIES, {"schema_version": SCHEMA_VERSION, "deliveries": lst})

    # ---- resolved sources ----
    def load_resolved(self) -> dict:
        d = self._load(RESOLVED, {"schema_version": SCHEMA_VERSION, "wallets": {}})
        return d.get("wallets", {})

    def save_resolved(self, wallets: dict):
        self._save(RESOLVED, {"schema_version": SCHEMA_VERSION, "wallets": wallets})

    # ---- summary for observability ----
    def summary(self) -> dict:
        cost = self.load_cost()
        return {
            "month": cost.get("month"),
            "monthly_cost_usd": round(float(cost.get("estimated_cost_usd", 0.0)), 4),
            "monthly_calls": cost.get("calls", 0),
            "seen_count": len(self.load_seen()),
            "deliveries_count": len(self.load_deliveries()),
        }

    def reload(self):
        """Re-read from disk after an external sync (e.g. git_state pull)."""
        # StateStore is stateless per call (loads on demand), so nothing cached to drop.
        pass
