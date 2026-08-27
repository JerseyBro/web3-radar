from __future__ import annotations
import json
import os
import time
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "storage" / "state"
SCHEMA_VERSION = 1

# Files persisted on radar-state branch
SEEN = "seen.json"
CLUSTERS = "clusters.json"
COST = "cost.json"
DELIVERIES = "deliveries.json"
RESOLVED = "resolved_sources.json"


def _atomic_write(path: Path, data: Any):
    """Write JSON atomically: write to .tmp then rename. Never corrupt the live file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _now_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


class StateStore:
    """Cross-run persistent state. Files are synced to the radar-state git branch by git_state.py."""

    def __init__(self, state_dir: Path | None = None):
        self.dir = state_dir or STATE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

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
            return {"schema_version": SCHEMA_VERSION, "data": data}
        except Exception:
            # corrupt file -> auto reinit, do not crash pipeline
            return {"schema_version": SCHEMA_VERSION}

    def _save(self, name: str, data: dict):
        data["schema_version"] = SCHEMA_VERSION
        _atomic_write(self.dir / name, data)

    # ---- seen (cross-run event dedupe) ----
    def load_seen(self) -> set[str]:
        d = self._load(SEEN, {"schema_version": SCHEMA_VERSION, "ids": []})
        return set(d.get("ids", []))

    def add_seen(self, ids: list[str]):
        s = self.load_seen()
        s.update(ids)
        # cap to avoid unbounded growth (keep last 20000)
        ids_list = sorted(s)[-20000:]
        self._save(SEEN, {"schema_version": SCHEMA_VERSION, "ids": ids_list})

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
