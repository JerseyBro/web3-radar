from pathlib import Path
import tempfile
from storage.state import StateStore
from pipeline.cost_guard import CostGuard

def _state():
    d = Path(tempfile.mkdtemp())
    return StateStore(state_dir=d)

def test_budget_block():
    with tempfile.TemporaryDirectory() as td:
        state = StateStore(state_dir=Path(td))
        g = CostGuard(state=state, budget_usd=0.01, max_calls_per_run=20, pricing={"gpt-4o-mini":{"input":1.0,"output":4.0}})
        ok, _ = g.can_call(0.001)
        assert ok
        g.record("gpt-4o-mini", 1000000, 0, "industry")  # cost 1.0 > budget
        ok2, reason = g.can_call(0.001)
        assert not ok2
        assert "budget" in reason.lower()

def test_max_calls():
    with tempfile.TemporaryDirectory() as td:
        state = StateStore(state_dir=Path(td))
        g = CostGuard(state=state, budget_usd=5, max_calls_per_run=1)
        g.record("gpt-4o-mini", 10, 10, "industry")
        ok, reason = g.can_call()
        assert not ok
        assert "max" in reason.lower()

def test_monthly_accumulation():
    with tempfile.TemporaryDirectory() as td:
        state = StateStore(state_dir=Path(td))
        g = CostGuard(state=state, budget_usd=5, max_calls_per_run=100, pricing={"gpt-4o-mini":{"input":1.0,"output":4.0}})
        for _ in range(3):
            g.record("gpt-4o-mini", 100000, 0, "industry")  # 0.1 each
        # reload from disk (simulate new run)
        state2 = StateStore(state_dir=Path(td))
        assert state2.monthly_cost_usd() == 0.3
        assert state2.summary()["monthly_calls"] == 3

def test_month_rollover():
    with tempfile.TemporaryDirectory() as td:
        state = StateStore(state_dir=Path(td))
        # manually set old month
        import json
        (Path(td)/"cost.json").write_text(json.dumps({"schema_version":1,"month":"2000-01","estimated_cost_usd":9.0,"calls":99,"input_tokens":0,"output_tokens":0}))
        g = CostGuard(state=state, budget_usd=5, max_calls_per_run=100)
        assert g.can_call(0.001)[0] is True  # old month cost ignored
        assert state.monthly_cost_usd() == 0.0  # rolled over
