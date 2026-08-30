from __future__ import annotations
import logging
from dataclasses import dataclass
from storage.state import StateStore

logger = logging.getLogger(__name__)

@dataclass
class CostRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: float
    radar: str

class CostGuard:
    """Real monthly budget: persisted via StateStore (radar-state branch).

    - Budget is evaluated across the whole calendar month (not per-run).
    - On new month, cost.json rolls over automatically.
    - Reaching the budget stops non-essential AI calls but never aborts the deterministic pipeline.
    """
    def __init__(self, budget_usd: float = 5.0, max_calls_per_run: int = 20, pricing: dict | None = None, state: StateStore | None = None):
        self.budget_usd = budget_usd
        self.max_calls_per_run = max_calls_per_run
        self.calls_this_run = 0
        self.cost_this_run = 0.0
        self.pricing = pricing or {}
        self.records: list[CostRecord] = []
        self.state = state
        if state is not None:
            from storage import store as _store
            self._store = _store
            self.monthly = state.load_cost()
        else:
            from storage import store as _store
            self._store = _store
            self.monthly = _store.load_cost()

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        p = self.pricing.get(model)
        if p is None:
            return 0.0
        return (input_tokens / 1_000_000) * p["input"] + (output_tokens / 1_000_000) * p["output"]

    def is_pricing_known(self, model: str) -> bool:
        return model in self.pricing

    def can_call(self, estimated_cost: float = 0.001) -> tuple[bool, str]:
        if self.calls_this_run >= self.max_calls_per_run:
            return False, f"max calls per run reached ({self.max_calls_per_run})"
        if self.monthly.get("estimated_cost_usd", 0.0) + self.cost_this_run + estimated_cost > self.budget_usd:
            return False, f"MONTHLY budget exceeded ({self.budget_usd} USD). Stopping non-essential AI. Candidates preserved."
        return True, ""

    def record(self, model: str, input_tokens: int, output_tokens: int, radar: str, provider: str | None = None, cost_unknown: bool = False, usage_unavailable: bool = False) -> float:
        import time

        if cost_unknown or not self.is_pricing_known(model):
            cost = 0.0
            logger.info(f"COST_UNKNOWN model={model} provider={provider or '?'} — tracking tokens only")
        else:
            cost = self.estimate_cost(model, input_tokens, output_tokens)
        if usage_unavailable:
            logger.info(f"USAGE_UNKNOWN model={model} provider={provider or '?'} — cost estimated from token guess")

        if self.state is not None:
            self.state.record_cost(model, input_tokens, output_tokens, cost)
        else:
            self._store.add_cost(model, input_tokens, output_tokens, cost)
        self.monthly = self.state.load_cost() if self.state else self._store.load_cost()
        self.cost_this_run += cost
        self.calls_this_run += 1
        self.records.append(CostRecord(model, input_tokens, output_tokens, cost, time.time(), radar))
        return cost

    def summary(self) -> dict:
        return {
            "calls_this_run": self.calls_this_run,
            "cost_this_run": round(self.cost_this_run, 4),
            "monthly_cost": round(self.monthly.get("estimated_cost_usd", 0.0), 4),
            "monthly_calls": self.monthly.get("calls", 0),
            "month": self.monthly.get("month"),
            "budget": self.budget_usd,
            "blocked": (self.monthly.get("estimated_cost_usd", 0.0) + self.cost_this_run) >= self.budget_usd,
        }

    def warning(self) -> str | None:
        if (self.monthly.get("estimated_cost_usd", 0.0) + self.cost_this_run) >= self.budget_usd:
            return "MONTHLY BUDGET EXCEEDED - AI calls stopped; deterministic pipeline continues, candidates preserved"
        return None
