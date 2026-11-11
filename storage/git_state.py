from __future__ import annotations
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
import logging
import re
from datetime import datetime
from pathlib import Path
from radar.schema import Event
from storage.state import (
    CANDIDATE_MAX_FILE_BYTES, CANDIDATE_MAX_ITEMS,
    LEGACY_SCHEMA_VERSION, SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)

BRANCH = "radar-state"
REQUIRED_STATE_FILES = ("seen.json", "cost.json", "deliveries.json")
CANDIDATE_STATE_FILES = {
    "candidates_industry.json": "industry",
    "candidates_competitor.json": "competitor",
}


def _validate_core_state(name: str, data: object) -> dict:
    """Reject a remote core file that StateStore would silently reset or misread."""
    if name in ("seen.json", "critical_alerts.json") and isinstance(data, list) and all(isinstance(eid, str) for eid in data):
        data = {"schema_version": LEGACY_SCHEMA_VERSION, "ids": data}
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
        raise ValueError(f"{name}: invalid schema")
    version = data["schema_version"]
    if version not in (LEGACY_SCHEMA_VERSION, SCHEMA_VERSION):
        raise ValueError(f"{name}: unsupported schema version")

    if name == "critical_alerts.json":
        ids = data.get("ids")
        if ids is None and version == LEGACY_SCHEMA_VERSION:
            legacy = data.get("data")
            ids = legacy.get("ids") if isinstance(legacy, dict) else legacy
        if not isinstance(ids, list) or any(not isinstance(eid, str) for eid in ids):
            raise ValueError(f"{name}: invalid alert ids")
    elif name == "seen.json":
        if version == LEGACY_SCHEMA_VERSION:
            ids = data.get("ids")
            if not isinstance(ids, list) or any(not isinstance(eid, str) for eid in ids):
                raise ValueError(f"{name}: invalid legacy ids")
        else:
            items = data.get("items")
            if not isinstance(items, dict):
                raise ValueError(f"{name}: invalid items")
            for eid, timestamp in items.items():
                if not isinstance(eid, str) or not isinstance(timestamp, str):
                    raise ValueError(f"{name}: invalid item")
                try:
                    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ValueError(f"{name}: invalid timestamp") from exc
    elif name == "cost.json":
        month = data.get("month")
        if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise ValueError(f"{name}: invalid month")
        cost = data.get("estimated_cost_usd")
        if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
            raise ValueError(f"{name}: invalid estimated cost")
        for key in ("calls", "input_tokens", "output_tokens"):
            value = data.get(key)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name}: invalid {key}")
    elif name == "deliveries.json":
        deliveries = data.get("deliveries")
        if version == LEGACY_SCHEMA_VERSION and isinstance(deliveries, dict):
            migrated = []
            for compound_key, value in deliveries.items():
                if not isinstance(compound_key, str) or ":" not in compound_key or not isinstance(value, dict):
                    raise ValueError(f"{name}: invalid legacy entry")
                target, key = compound_key.split(":", 1)
                if not target or not key or not isinstance(value.get("status"), str):
                    raise ValueError(f"{name}: invalid legacy entry")
                migrated.append({"target": target, "key": key, "status": value["status"],
                                 "delivered_at": value.get("delivered_at")})
            data = {"schema_version": SCHEMA_VERSION, "deliveries": migrated}
        elif not isinstance(deliveries, list):
            raise ValueError(f"{name}: invalid deliveries")
        for entry in data["deliveries"]:
            if not isinstance(entry, dict) or any(
                not isinstance(entry.get(key), str) or not entry[key]
                for key in ("target", "key", "status")
            ):
                raise ValueError(f"{name}: invalid delivery entry")
    return data


def _validate_candidate_state(name: str, data: object, file_bytes: int) -> None:
    """Reject remote candidate files that StateStore would silently discard."""
    radar = CANDIDATE_STATE_FILES[name]
    if file_bytes > CANDIDATE_MAX_FILE_BYTES:
        raise ValueError(f"{name}: exceeds size limit")
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"{name}: invalid schema")
    if data.get("radar") != radar:
        raise ValueError(f"{name}: radar mismatch")
    rows = data.get("events")
    if not isinstance(rows, list) or len(rows) > CANDIDATE_MAX_ITEMS:
        raise ValueError(f"{name}: invalid events list")
    for index, row in enumerate(rows):
        try:
            event = Event.model_validate(row)
        except Exception:
            raise ValueError(f"{name}: invalid event at index {index}") from None
        if event.radar.value != radar:
            raise ValueError(f"{name}: event radar mismatch at index {index}")


def _redact(text: str) -> str:
    """Remove embedded credentials from git commands and stderr before logging."""
    safe = re.sub(r"https://[^\s/@:]+:[^\s/@]+@", "https://***:***@", str(text))
    for key in ("GITHUB_TOKEN", "STATE_PUSH_TOKEN"):
        value = os.getenv(key)
        if value:
            safe = safe.replace(value, "***")
    return safe


def _run(cmd: list[str], cwd: str | None = None, check: bool = True):
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and res.returncode != 0:
        command = _redact(" ".join(cmd))
        stderr = _redact(res.stderr.strip())[:300]
        raise RuntimeError(f"cmd {command} failed: {stderr}")
    return res


def _repo_url() -> str | None:
    # Optional override (useful for local testing / repo renames)
    override = os.getenv("RADAR_STATE_REPO_URL")
    if override:
        return override
    token = os.getenv("GITHUB_TOKEN") or os.getenv("STATE_PUSH_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    if token and repo:
        return f"https://x-access-token:{token}@github.com/{repo}.git"
    return None


def _remote_url() -> str | None:
    url = _repo_url()
    if not url and os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        raise RuntimeError("[state] GitHub Actions state remote is not configured")
    return url


def _branch_exists(url: str) -> bool:
    # A missing branch is valid on the first run. Authentication and network
    # errors are distinct and must stop the run before any external delivery.
    res = _run(["git", "ls-remote", "--exit-code", "--heads", url, BRANCH], check=False)
    if res.returncode == 0:
        return True
    if res.returncode == 2:
        return False
    raise RuntimeError(f"[state] branch check failed: {_redact(res.stderr.strip())[:300]}")


def pull_state(state_dir: Path) -> bool:
    """Load remote state, allowing only local mode or first-run branch absence."""
    url = _remote_url()
    if not url:
        logger.info("[state] No remote configured; using local state files only.")
        return False
    if not _branch_exists(url):
        logger.info("[state] Remote state branch absent; first run will initialize it.")
        return False
    tmp = tempfile.mkdtemp(prefix="radar-state-")
    try:
        _run(["git", "clone", "--branch", BRANCH, "--depth", "1", url, tmp])
        src = Path(tmp) / "storage" / "state"
        missing = [name for name in REQUIRED_STATE_FILES if not (src / name).is_file()]
        if missing:
            raise RuntimeError(f"remote state is missing required files: {', '.join(missing)}")
        files = list(src.glob("*.json"))
        validated: dict[str, dict] = {}
        for f in files:
            if f.name in CANDIDATE_STATE_FILES and f.stat().st_size > CANDIDATE_MAX_FILE_BYTES:
                raise ValueError(f"{f.name}: exceeds size limit")
            data = json.loads(f.read_text(encoding="utf-8"))
            if f.name in REQUIRED_STATE_FILES or f.name == "critical_alerts.json":
                validated[f.name] = _validate_core_state(f.name, data)
            elif f.name in CANDIDATE_STATE_FILES:
                _validate_candidate_state(f.name, data, f.stat().st_size)
        for f in files:
            if f.name in validated:
                (state_dir / f.name).write_text(json.dumps(validated[f.name], indent=2), encoding="utf-8")
            else:
                shutil.copy(f, state_dir / f.name)
        logger.info(f"[state] Pulled radar-state ({len(files)}) files")
        return True
    except Exception as e:
        raise RuntimeError(f"[state] pull failed: {_redact(str(e))}") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def push_state(state_dir: Path, summary: str = "") -> bool:
    """Atomically commit & push state_dir files to radar-state branch. No force push. Retries on conflict."""
    url = _remote_url()
    if not url:
        logger.info("[state] No remote configured; keeping local state files only.")
        return False
    created = not _branch_exists(url)
    tmp = tempfile.mkdtemp(prefix="radar-state-")
    try:
        if not created:
            _run(["git", "clone", "--branch", BRANCH, "--depth", "1", url, tmp])
        else:
            _run(["git", "init", tmp])
            _run(["git", "-C", tmp, "checkout", "-b", BRANCH])
            _run(["git", "-C", tmp, "remote", "add", "origin", url])
        dst = Path(tmp) / "storage" / "state"
        dst.mkdir(parents=True, exist_ok=True)
        for f in state_dir.glob("*.json"):
            shutil.copy(f, dst / f.name)
        if created:
            # Establish a complete core state on a genuinely new branch, even
            # when the first scan produced no events or billable model calls.
            defaults = {
                "seen.json": {"schema_version": SCHEMA_VERSION, "items": {}},
                "cost.json": {
                    "schema_version": SCHEMA_VERSION,
                    "month": time.strftime("%Y-%m", time.gmtime()),
                    "estimated_cost_usd": 0.0, "calls": 0,
                    "input_tokens": 0, "output_tokens": 0,
                },
                "deliveries.json": {"schema_version": SCHEMA_VERSION, "deliveries": []},
            }
            for name, data in defaults.items():
                path = dst / name
                if not path.exists():
                    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        _run(["git", "-C", tmp, "config", "user.email", "radar@local"])
        _run(["git", "-C", tmp, "config", "user.name", "web3-radar"])
        _run(["git", "-C", tmp, "add", "-A"])
        # commit only if there is a diff
        diff = _run(["git", "-C", tmp, "status", "--porcelain"])
        if diff.stdout.strip():
            msg = f"chore(state): sync {time.strftime('%Y-%m-%d %H:%M')} {summary}".strip()
            _run(["git", "-C", tmp, "commit", "-m", msg])
        else:
            logger.info("[state] No state changes to commit.")
            return True
        # push with conflict retry, no force
        for attempt in range(5):
            try:
                if not created:
                    _run(["git", "-C", tmp, "pull", "--rebase", "origin", BRANCH])
                _run(["git", "-C", tmp, "push", "origin", BRANCH], check=True)
                logger.info("[state] Pushed radar-state successfully.")
                return True
            except Exception as e:
                if attempt == 4:
                    raise RuntimeError(f"[state] push failed after retries: {_redact(str(e))}") from e
                created = False
                logger.warning(f"[state] push conflict, retrying ({attempt+1})...")
                time.sleep(2 ** attempt)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
