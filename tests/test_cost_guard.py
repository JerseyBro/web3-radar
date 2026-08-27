from pathlib import Path
import tempfile
from pipeline.cost_guard import CostGuard

def test_budget_block():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)/"cost.json"
        g = CostGuard(budget_usd=0.01, max_calls_per_run=2, state_path=p, pricing={"gpt-4o-mini":{"input":1.0,"output":4.0}})
        ok, _ = g.can_call(0.001)
        assert ok
        g.record("gpt-4o-mini", 1000000, 0, "industry")  # cost 1.0 > budget
        ok2, reason = g.can_call(0.001)
        assert not ok2

def test_max_calls():
    g = CostGuard(budget_usd=5, max_calls_per_run=1)
    g.record("gpt-4o-mini", 10, 10, "industry")
    ok, _ = g.can_call()
    assert not ok
