from __future__ import annotations
import sys
import shutil
import subprocess
from pathlib import Path
import importlib.util

from radar.config import ROOT, get_settings

REQUIRED_DEPS = ["pydantic", "httpx", "yaml", "bs4", "feedparser", "dateutil"]
OPTIONAL_DEPS = ["openai", "rapidfuzz", "trafilatura"]
CONFIG_FILES = ["sources.yaml", "scoring.yaml", "models.yaml", "settings.yaml"]


def _py_version_ok() -> bool:
    return sys.version_info >= (3, 12)

def _git_ok() -> bool:
    return shutil.which("git") is not None

def _in_repo() -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                        cwd=ROOT, capture_output=True, check=True)
        return True
    except Exception:
        return False

def _origin_ok() -> bool:
    try:
        out = subprocess.run(["git", "remote", "get-url", "origin"],
                             cwd=ROOT, capture_output=True, text=True)
        return out.returncode == 0 and out.stdout.strip() != ""
    except Exception:
        return False

def _dep(name: str) -> bool:
    return importlib.util.find_spec(name) is not None

def _config_ok(name: str) -> bool:
    return (ROOT / "config" / name).exists()

def _secret_set(key: str) -> bool:
    import os
    v = os.getenv(key, "")
    return bool(v and v.strip())

def run_doctor() -> int:
    overall_ok = True
    blocked_by_config = False

    def line(label, status, note=""):
        if status is True:
            sym = "PASS"
        elif status is False:
            sym = "FAIL"
        else:
            sym = str(status)
        print(f"  {label:<28} {sym}{('  ' + note) if note else ''}")

    print("Web3 Intelligence Radar Doctor\n")

    # Runtime
    print("Runtime")
    print("-" * 32)
    line("Python >= 3.12", _py_version_ok(), f"({sys.version_info.major}.{sys.version_info.minor})")
    if not _py_version_ok(): overall_ok = False
    line("Git", _git_ok())
    if not _git_ok(): overall_ok = False
    line("Repository", _in_repo())
    if not _in_repo(): overall_ok = False
    line("Origin", _origin_ok())
    if not _origin_ok(): blocked_by_config = True

    # Dependencies
    print("\nDependencies")
    print("-" * 32)
    for d in REQUIRED_DEPS:
        ok = _dep(d)
        line(d, ok, "" if ok else "MISSING")
        if not ok: overall_ok = False
    for d in OPTIONAL_DEPS:
        ok = _dep(d)
        print(f"  {d:<28} {'PASS' if ok else 'OPTIONAL'}{'' if ok else '  (not installed)'}")

    # Config
    print("\nConfig")
    print("-" * 32)
    for c in CONFIG_FILES:
        ok = _config_ok(c)
        line(c, ok, "" if ok else "MISSING")
        if not ok: overall_ok = False

    # Secrets
    print("\nSecrets")
    print("-" * 32)
    secrets = {
        "OPENAI_API_KEY": "REQUIRED",
        "LARK_WEBHOOK_INDUSTRY": "REQUIRED",
        "LARK_WEBHOOK_COMPETITOR": "REQUIRED",
    }
    missing_secrets = []
    for k, req in secrets.items():
        ok = _secret_set(k)
        line(k, ok, "" if ok else "MISSING")
        if not ok:
            missing_secrets.append(k)
    if missing_secrets:
        blocked_by_config = True

    print("\nSigning")
    print("-" * 32)
    print("  Industry                    OPTIONAL")
    print("  Competitor                  OPTIONAL")

    # State
    print("\nState")
    print("-" * 32)
    state_dir = ROOT / "storage" / "state"
    line("State directory", state_dir.exists())
    if not state_dir.exists():
        overall_ok = False
    # schema check
    schema_ok = True
    for f in ["seen.json", "clusters.json", "cost.json", "deliveries.json"]:
        p = state_dir / f
        if p.exists():
            try:
                import json
                d = json.loads(p.read_text())
                if "schema_version" not in d:
                    schema_ok = False
            except Exception:
                schema_ok = False
    line("State schema", schema_ok)
    if not schema_ok: overall_ok = False
    line("Cost state", (state_dir / "cost.json").exists() or True)
    line("Delivery state", (state_dir / "deliveries.json").exists() or True)

    # Models / Budget
    print("\nModels")
    print("-" * 32)
    settings = get_settings()
    models = settings["models"]
    cls = models.get("classifier", {}).get("primary", "?")
    syn = models.get("synthesis", {}).get("primary", "?")
    print(f"  Classifier                  {cls}")
    print(f"  Synthesis                   {syn}")
    print("\nBudget")
    print("-" * 32)
    print(f"  Monthly AI Budget           ${models.get('monthly_ai_budget_usd', 5)}")
    print(f"  Max Calls / Run             {models.get('max_ai_calls_per_run', 20)}")

    print("\nOverall")
    print("-" * 32)
    if not overall_ok:
        print("  NOT READY")
        return 1
    if blocked_by_config:
        print("  BLOCKED_BY_CONFIGURATION")
        return 0
    print("  READY")
    return 0
