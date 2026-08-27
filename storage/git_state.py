from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BRANCH = "radar-state"


def _run(cmd: list[str], cwd: str | None = None, check: bool = True):
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"cmd {' '.join(cmd)} failed: {res.stderr.strip()[:300]}")
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


def pull_state(state_dir: Path) -> bool:
    """Load state files from radar-state branch into local state_dir. No-op if not in CI."""
    url = _repo_url()
    if not url:
        logger.info("[state] No CI repo token; using local state files only.")
        return False
    tmp = tempfile.mkdtemp(prefix="radar-state-")
    try:
        _run(["git", "clone", "--branch", BRANCH, "--depth", "1", url, tmp])
        src = Path(tmp) / "storage" / "state"
        if src.exists():
            for f in src.glob("*.json"):
                shutil.copy(f, state_dir / f.name)
            logger.info(f"[state] Pulled radar-state ({len(list(src.glob('*.json')))}) files")
        return True
    except Exception as e:
        logger.warning(f"[state] pull failed (continuing with local): {e}")
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def push_state(state_dir: Path, summary: str = "") -> bool:
    """Atomically commit & push state_dir files to radar-state branch. No force push. Retries on conflict."""
    url = _repo_url()
    if not url:
        logger.info("[state] No CI repo token; skipping remote state push.")
        return False
    tmp = tempfile.mkdtemp(prefix="radar-state-")
    try:
        try:
            _run(["git", "clone", "--branch", BRANCH, "--depth", "1", url, tmp])
            created = False
        except Exception:
            # branch likely does not exist yet -> initialize
            _run(["git", "init", tmp])
            _run(["git", "-C", tmp, "checkout", "-b", BRANCH])
            _run(["git", "-C", tmp, "remote", "add", "origin", url])
            created = True
        dst = Path(tmp) / "storage" / "state"
        dst.mkdir(parents=True, exist_ok=True)
        for f in state_dir.glob("*.json"):
            shutil.copy(f, dst / f.name)
        _run(["git", "-C", tmp, "config", "user.email", "radar@local"])
        _run(["git", "-C", tmp, "config", "user.name", "web3-radar"])
        _run(["git", "-C", tmp, "add", "-A"])
        # commit only if there is a diff
        diff = _run(["git", "-C", tmp, "status", "--porcelain"], check=False)
        if diff.stdout.strip():
            msg = f"chore(state): sync {time.strftime('%Y-%m-%d %H:%M')} {summary}".strip()
            _run(["git", "-C", tmp, "commit", "-m", msg], check=False)
        else:
            logger.info("[state] No state changes to commit.")
            return True
        # push with conflict retry, no force
        for attempt in range(5):
            try:
                if not created:
                    _run(["git", "-C", tmp, "pull", "--rebase", "origin", BRANCH], check=False)
                _run(["git", "-C", tmp, "push", "origin", BRANCH], check=True)
                logger.info("[state] Pushed radar-state successfully.")
                return True
            except Exception as e:
                if attempt == 4:
                    logger.error(f"[state] push failed after retries: {e}")
                    return False
                logger.warning(f"[state] push conflict, retrying ({attempt+1})...")
                time.sleep(2 ** attempt)
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
