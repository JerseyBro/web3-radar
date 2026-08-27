import os
import json
from pathlib import Path
import tempfile

import httpx

from storage.state import StateStore
from outputs.lark import LarkOutput, _sign
from outputs.local_http import LocalHTTPOutput
from outputs.file import FileOutput
from outputs.router import OutputRouter
from outputs.base import DeliveryContext, DeliveryStatus
from radar.report import Report


def _ctx(radar="industry", state=None, dry_run=False, force=False):
    return DeliveryContext(radar=radar, report_id="rpt-1", title="t", dry_run=dry_run, force=force, state=state)


def _report(radar="industry", kind="weekly"):
    return Report(radar=radar, period="2026-W35", kind=kind, markdown="# hi", events=[])


def test_lark_success_response():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"code": 0, "msg": "success"})
    transport = httpx.MockTransport(handler)
    os.environ["LARK_WEBHOOK_INDUSTRY"] = "https://lark.example/hook"
    out = LarkOutput()
    with httpx.Client(transport=transport) as client:
        # patch internal to use mocked client? send_lark uses its own client.
        pass
    # send_lark creates its own client; use monkeypatch via transport on global? Instead call deliver with real network blocked.
    # We test the response parsing path by calling send_lark with a transport-injected client through monkeypatch is complex;
    # Instead validate via LarkOutput using a stubbed send by overriding httpx.Client.
    import outputs.lark as L
    orig = httpx.Client
    httpx.Client = lambda *a, **k: orig(transport=transport)
    try:
        res = out.deliver(_report(), _ctx())
    finally:
        httpx.Client = orig
    assert res.success
    assert res.status == DeliveryStatus.SUCCESS.value
    assert len(calls) == 1


def test_lark_business_failure():
    def handler(req):
        return httpx.Response(200, json={"code": 19021, "msg": "keyword blocked"})
    transport = httpx.MockTransport(handler)
    os.environ["LARK_WEBHOOK_INDUSTRY"] = "https://lark.example/hook"
    out = LarkOutput()
    import outputs.lark as L
    orig = httpx.Client
    httpx.Client = lambda *a, **k: orig(transport=transport)
    try:
        res = out.deliver(_report(), _ctx())
    finally:
        httpx.Client = orig
    assert not res.success
    assert res.error_type == "KEYWORD_REJECTED"


def test_lark_signing():
    sig = _sign("secret", "123")
    assert isinstance(sig, str) and len(sig) > 0
    # deterministic
    assert _sign("secret", "123") == sig


def test_lark_dry_run_cannot_push():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"code": 0})
    transport = httpx.MockTransport(handler)
    os.environ["LARK_WEBHOOK_INDUSTRY"] = "https://lark.example/hook"
    out = LarkOutput()
    import outputs.lark as L
    orig = httpx.Client
    httpx.Client = lambda *a, **k: orig(transport=transport)
    try:
        res = out.deliver(_report(), _ctx(dry_run=True))
    finally:
        httpx.Client = orig
    assert res.status == DeliveryStatus.PREVIEW.value
    assert calls == [], "dry-run must not send"


def test_lark_timeout_retry_then_success():
    state = {"n": 0}
    def handler(req):
        state["n"] += 1
        if state["n"] < 3:
            raise httpx.TimeoutException("timed out")
        return httpx.Response(200, json={"code": 0})
    transport = httpx.MockTransport(handler)
    os.environ["LARK_WEBHOOK_INDUSTRY"] = "https://lark.example/hook"
    out = LarkOutput(retry_max=4, backoff_base=0.0)
    import outputs.lark as L
    orig = httpx.Client
    httpx.Client = lambda *a, **k: orig(transport=transport)
    try:
        res = out.deliver(_report(), _ctx())
    finally:
        httpx.Client = orig
    assert res.success
    assert state["n"] == 3
    assert res.attempts >= 3


def test_local_http_payload():
    captured = {}
    def handler(req):
        captured["body"] = json.loads(req.content)
        captured["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})
    transport = httpx.MockTransport(handler)
    os.environ["LOCAL_WEBHOOK_URL"] = "https://local.example/api/radar"
    os.environ["LOCAL_WEBHOOK_TOKEN"] = "tok123"
    out = LocalHTTPOutput()
    import outputs.local_http as LH
    orig = httpx.Client
    httpx.Client = lambda *a, **k: orig(transport=transport)
    try:
        res = out.deliver(_report(), _ctx())
    finally:
        httpx.Client = orig
    assert res.success
    b = captured["body"]
    assert b["schema_version"] == "1"
    assert b["event_type"] == "weekly_report"
    assert b["radar"] == "industry"
    assert "report" in b and "meta" in b
    assert captured["auth"] == "Bearer tok123"


def test_local_http_failure_isolation():
    def handler(req):
        return httpx.Response(500, json={"err": 1})
    transport = httpx.MockTransport(handler)
    os.environ["LOCAL_WEBHOOK_URL"] = "https://local.example/api/radar"
    router = OutputRouter(["local-http", "file"], state=StateStore(state_dir=Path(tempfile.mkdtemp())),
                          settings={"delivery": {}})
    import outputs.local_http as LH
    orig = httpx.Client
    httpx.Client = lambda *a, **k: orig(transport=transport)
    try:
        results = router.deliver(_report(), _ctx())
    finally:
        httpx.Client = orig
    by_t = {r.target: r for r in results}
    assert by_t["local-http"].success is False
    assert by_t["file"].success is True  # file still written


def test_delivery_idempotency_and_force():
    state = StateStore(state_dir=Path(tempfile.mkdtemp()))
    # first delivery
    def handler(req):
        return httpx.Response(200, json={"code": 0})
    transport = httpx.MockTransport(handler)
    os.environ["LARK_WEBHOOK_INDUSTRY"] = "https://lark.example/hook"
    import outputs.lark as L
    orig = httpx.Client
    httpx.Client = lambda *a, **k: orig(transport=transport)
    try:
        out = LarkOutput()
        r1 = out.deliver(_report(), _ctx(state=state))
        # second time same report_id -> skipped
        r2 = out.deliver(_report(), _ctx(state=state))
        # force push -> sends again
        r3 = out.deliver(_report(), _ctx(state=state, force=True))
    finally:
        httpx.Client = orig
    assert r1.success
    assert r2.status == DeliveryStatus.SKIPPED.value
    assert r3.success


def test_router_multi_target():
    def handler(req):
        return httpx.Response(200, json={"code": 0})
    transport = httpx.MockTransport(handler)
    os.environ["LARK_WEBHOOK_INDUSTRY"] = "https://lark.example/hook"
    router = OutputRouter(["lark", "file"], state=StateStore(state_dir=Path(tempfile.mkdtemp())), settings={"delivery": {}})
    import outputs.lark as L
    orig = httpx.Client
    httpx.Client = lambda *a, **k: orig(transport=transport)
    try:
        results = router.deliver(_report(), _ctx())
    finally:
        httpx.Client = orig
    assert {r.target for r in results} == {"lark", "file"}
    assert all(r.success for r in results)
