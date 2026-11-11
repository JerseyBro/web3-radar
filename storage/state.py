from __future__ import annotations
import json
import os
import time
import tempfile
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from radar.report import public_source_url
from radar.schema import Event

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
CRITICAL_ALERTS = "critical_alerts.json"
CANDIDATE_RETENTION_DAYS = 14
CANDIDATE_MAX_ITEMS = 500
CANDIDATE_MAX_FILE_BYTES = 4 * 1024 * 1024
_CANDIDATE_TIERS = {"archive", "weekly", "important", "critical"}
_RADARS = {"industry", "competitor"}
_WEB_URL = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_ACCESS_KEY = re.compile(r"(^|[_-])(token|secret|signature|sig|credential|auth|session)($|[_-])")
_ACCESS_KEY_EXACT = {
    "key", "api_key", "apikey", "access_key", "accesskey", "awsaccesskeyid",
    "authorization", "oauth", "bearer", "code", "auth_code", "oauth_code",
    "authorization_code", "invite_code",
}

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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _access_bearing_url(value: str, depth: int = 0) -> bool:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return True
    if parsed.username is not None or parsed.password is not None:
        return True
    if host in {"hooks.slack.com", "open.feishu.cn", "open.larksuite.com"} and (
        "/services/" in parsed.path or "/hook/" in parsed.path
    ):
        return True
    if host in {"discord.com", "discordapp.com"} and "/api/webhooks/" in parsed.path:
        return True
    if host == "api.telegram.org" and parsed.path.startswith("/bot"):
        return True
    if re.search(r"/(?:webhooks?|hooks?)/[A-Za-z0-9_-]{16,}", parsed.path, re.IGNORECASE):
        return True
    for section in (parsed.query, parsed.fragment):
        for key, item in parse_qsl(section.replace(";", "&"), keep_blank_values=True):
            normalized = key.lower().replace(".", "_")
            if _ACCESS_KEY.search(normalized) or normalized in _ACCESS_KEY_EXACT:
                return True
            if depth < 2 and any(_access_bearing_url(url, depth + 1) for url in _WEB_URL.findall(item)):
                return True
    return False


def _public_source_url(value: str) -> bool:
    if public_source_url(value) is None or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value)
        parsed.port  # reject malformed ports
    except ValueError:
        return False
    return not _access_bearing_url(value)


def _candidate_file(radar: str) -> str:
    if radar not in _RADARS:
        raise ValueError(f"invalid radar: {radar!r}")
    return f"candidates_{radar}.json"


def _contains_access_url(value: Any) -> bool:
    if isinstance(value, str):
        return any(_access_bearing_url(url) for url in _WEB_URL.findall(value))
    if isinstance(value, list):
        return any(_contains_access_url(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_access_url(item) for item in value.values())
    return False


def _candidate_payload(event: Event, radar: str, now: datetime) -> dict | None:
    """Keep a bounded Event projection without opaque collector metadata."""
    if not isinstance(event, Event) or event.radar.value != radar or event.tier not in _CANDIDATE_TIERS:
        return None
    published = _utc_datetime(event.published_at)
    if published is None or published < now - timedelta(days=CANDIDATE_RETENTION_DAYS):
        return None
    if (published > now + timedelta(seconds=60) or not event.event_id
            or len(event.event_id) > 128 or not _public_source_url(event.source_url)):
        return None
    payload = event.model_dump(mode="json", exclude={"raw_meta"})
    # Treat model output and source text as untrusted. A URL with credentials
    # must not be committed to the radar-state branch in any cached field.
    if _contains_access_url(payload):
        return None
    limits = {
        "entity": 120, "source": 120, "title": 300,
        "excerpt": 800, "ai_summary": 600, "why_it_matters": 600,
        "wallet_implication": 600, "developer_action": 600,
        "cluster_id": 128, "duplicate_of": 128,
    }
    for key, limit in limits.items():
        if isinstance(payload.get(key), str):
            payload[key] = payload[key][:limit]
    payload["tags"] = [str(tag)[:60] for tag in payload.get("tags", [])[:20]]
    payload["published_at"] = published.isoformat()
    return payload


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

    # ---- weekly candidates (cross-run, bounded, UTC publication window) ----
    def _load_candidate_rows(self, radar: str) -> list:
        name = _candidate_file(radar)
        path = self.dir / name
        if path.exists() and path.stat().st_size > CANDIDATE_MAX_FILE_BYTES:
            return []
        data = self._load(name, {"schema_version": SCHEMA_VERSION, "radar": radar, "events": []})
        if data.get("schema_version") != SCHEMA_VERSION or data.get("radar") != radar:
            return []
        rows = data.get("events")
        return rows if isinstance(rows, list) else []

    def _validated_candidates(self, radar: str, now: datetime) -> dict[str, dict]:
        candidates: dict[str, dict] = {}
        for row in self._load_candidate_rows(radar):
            try:
                payload = _candidate_payload(Event.model_validate(row), radar, now)
            except Exception:
                continue
            if payload is not None:
                candidates[payload["event_id"]] = payload
        return candidates

    @staticmethod
    def _ordered_candidates(candidates: dict[str, dict]) -> list[dict]:
        return sorted(
            candidates.values(),
            key=lambda item: (-datetime.fromisoformat(item["published_at"]).timestamp(),
                              -item["score"], item["event_id"]),
        )[:CANDIDATE_MAX_ITEMS]

    def record_candidates(self, radar: str, events: list[Event]) -> int:
        """Merge eligible events into a 14-day cache synced by git_state's *.json glob.

        Undated events are excluded: a later runner cannot know which week an
        old snapshot belongs to. The fresh weekly scan can still report them.
        """
        name = _candidate_file(radar)
        now = _utc_now()
        candidates = self._validated_candidates(radar, now)
        for event in events:
            payload = _candidate_payload(event, radar, now)
            if payload is not None:
                candidates[payload["event_id"]] = payload
        rows = self._ordered_candidates(candidates)
        data = {"schema_version": SCHEMA_VERSION, "radar": radar, "events": rows}
        while rows and len(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")) > CANDIDATE_MAX_FILE_BYTES:
            rows.pop()
        self._save(name, data)
        return len(rows)

    def load_candidates(self, radar: str, lookback_days: int) -> list[Event]:
        """Read cached Events from a UTC 1..14-day publication window."""
        _candidate_file(radar)
        if not isinstance(lookback_days, int) or lookback_days < 1:
            raise ValueError("lookback_days must be a positive integer")
        now = _utc_now()
        cutoff = now - timedelta(days=min(lookback_days, CANDIDATE_RETENTION_DAYS))
        rows = self._ordered_candidates(self._validated_candidates(radar, now))
        return [Event.model_validate(row) for row in rows
                if datetime.fromisoformat(row["published_at"]) >= cutoff]

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

    # ---- critical alerts (namespace-scoped event idempotency) ----
    def _load_critical_ids(self) -> set[str]:
        data = self._load(CRITICAL_ALERTS, {"schema_version": SCHEMA_VERSION, "ids": []})
        # storage.store wrote schema v1 with `ids`; older bare lists are wrapped
        # by _load as `data`. Accept both without touching production state.
        ids = data.get("ids")
        if ids is None:
            legacy = data.get("data", [])
            ids = legacy.get("ids", []) if isinstance(legacy, dict) else legacy
        if not isinstance(ids, list):
            return set()
        return {str(event_id) for event_id in ids if event_id}

    def is_new_critical(self, event_id: str) -> bool:
        return str(event_id) not in self._load_critical_ids()

    def mark_critical_alerted(self, event_id: str) -> None:
        if not event_id:
            return
        event_id = str(event_id)
        ids = self._load_critical_ids()
        if event_id in ids:
            return
        ids.add(event_id)
        self._save(CRITICAL_ALERTS, {"schema_version": SCHEMA_VERSION, "ids": sorted(ids)})

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
