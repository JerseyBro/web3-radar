from __future__ import annotations
import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def get_settings():
    sources = load_yaml(ROOT / "config" / "sources.yaml")
    scoring = load_yaml(ROOT / "config" / "scoring.yaml")
    models = load_yaml(ROOT / "config" / "models.yaml")
    runtime = load_yaml(ROOT / "config" / "settings.yaml") or {}
    # Ensure runtime carries push + delivery defaults
    runtime.setdefault("push", models.get("push") or {"weekly_enabled": True, "critical_enabled": False})
    runtime.setdefault("delivery", {"default_outputs": ["file"], "retry_max": 3, "retry_backoff_base": 1.0})
    env_budget = os.getenv("MONTHLY_AI_BUDGET_USD")
    if env_budget:
        try:
            models["monthly_ai_budget_usd"] = float(env_budget)
        except: pass
    for k in ["MAX_AI_CALLS_PER_RUN", "MAX_WEEKLY_INPUT_EVENTS"]:
        v = os.getenv(k)
        if v:
            try:
                models[k.lower()] = int(v)
            except: pass
    push = runtime.get("push") or {"weekly_enabled": True, "critical_enabled": False}
    return {"sources": sources, "scoring": scoring, "models": models, "runtime": runtime, "push": push}
