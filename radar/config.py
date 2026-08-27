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
    return {"sources": sources, "scoring": scoring, "models": models}
