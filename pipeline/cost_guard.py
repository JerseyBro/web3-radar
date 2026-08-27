from __future__ import annotations
import json
import time
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class CostRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: float
    radar: str

class CostGuard:
    def __init__(self, budget_usd: float = 5.0, max_calls_per_run: int = 20, state_path: Path | None = None, pricing: dict | None = None):
        self.budget_usd = budget_usd
        self.max_calls_per_run = max_calls_per_run
        self.calls_this_run = 0
        self.cost_this_run = 0.0
        self.records: list[CostRecord] = []
        self.pricing = pricing or {}
        self.state_path = state_path
        # Load monthly cost from state file if exists
        self.monthly_cost = 0.0
        if state_path and state_path.exists():
            try:
                data = json.loads(state_path.read_text())
                # simple: sum last 30 days
                now = time.time()
                for r in data:
                    if now - r.get("timestamp", 0) < 30*24*3600:
                        self.monthly_cost += r.get("cost_usd", 0)
            except: pass

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        p = self.pricing.get(model) or self.pricing.get("gpt-4o-mini") or {"input":0.15,"output":0.6}
        return (input_tokens/1_000_000)*p["input"] + (output_tokens/1_000_000)*p["output"]

    def can_call(self, estimated_cost: float = 0.001) -> tuple[bool, str]:
        if self.calls_this_run >= self.max_calls_per_run:
            return False, f"max calls per run reached ({self.max_calls_per_run})"
        if self.monthly_cost + self.cost_this_run + estimated_cost > self.budget_usd:
            return False, f"monthly budget exceeded ({self.budget_usd} USD)"
        return True, ""

    def record(self, model: str, input_tokens: int, output_tokens: int, radar: str):
        cost = self.estimate_cost(model, input_tokens, output_tokens)
        rec = CostRecord(model, input_tokens, output_tokens, cost, time.time(), radar)
        self.records.append(rec)
        self.cost_this_run += cost
        self.monthly_cost += cost
        self.calls_this_run += 1
        # persist
        if self.state_path:
            try:
                existing = []
                if self.state_path.exists():
                    existing = json.loads(self.state_path.read_text())
                existing.append({"model":model,"input_tokens":input_tokens,"output_tokens":output_tokens,"cost_usd":cost,"timestamp":rec.timestamp,"radar":radar})
                # keep last 500
                existing = existing[-500:]
                self.state_path.parent.mkdir(parents=True, exist_ok=True)
                self.state_path.write_text(json.dumps(existing, indent=2))
            except: pass
        return cost

    def summary(self) -> dict:
        return {
            "calls_this_run": self.calls_this_run,
            "cost_this_run": round(self.cost_this_run, 4),
            "monthly_cost": round(self.monthly_cost, 4),
            "budget": self.budget_usd,
        }
