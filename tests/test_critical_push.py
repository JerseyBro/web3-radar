import os
import asyncio
from pathlib import Path
import tempfile

import httpx

from radar.schema import Event, RadarType
from storage import store as store_mod
from radar.report import Report


def _patch_critical(tmp: Path):
    store_mod.critical_alerts_path = lambda: tmp / "critical.json"


def _critical_res(event_id="crit-1"):
    e = Event(event_id=event_id, radar=RadarType.industry, source="s", source_url="https://x",
              title="Critical event", credibility=95, score=95, tier="critical")
    return {"critical_events": [e]}


def test_critical_push_disabled_by_config():
    tmp = Path(tempfile.mkdtemp())
    orig = store_mod.critical_alerts_path
    _patch_critical(tmp)
    try:
        from radar.cli import handle_critical
        calls = []
        def handler(req):
            calls.append(req)
            return httpx.Response(200, json={"code": 0})
        transport = httpx.MockTransport(handler)
        os.environ["LARK_WEBHOOK_INDUSTRY"] = "https://lark.example/hook"
        import outputs.lark as L
        orig_client = httpx.Client
        httpx.Client = lambda *a, **k: orig_client(transport=transport)
        try:
            asyncio.run(handle_critical(None, _critical_res(), "industry", can_push=False, force=False, dry_run=False))
        finally:
            httpx.Client = orig_client
        # Not delivered, not marked
        assert calls == []
        assert store_mod.is_new_critical("crit-1") is True
    finally:
        store_mod.critical_alerts_path = orig


def test_critical_push_enabled_delivers_and_marks():
    tmp = Path(tempfile.mkdtemp())
    orig_path = store_mod.critical_alerts_path
    _patch_critical(tmp)
    try:
        from radar.cli import handle_critical
        calls = []
        def handler(req):
            calls.append(req)
            return httpx.Response(200, json={"code": 0})
        transport = httpx.MockTransport(handler)
        os.environ["LARK_WEBHOOK_INDUSTRY"] = "https://lark.example/hook"
        import outputs.lark as L
        orig_client = httpx.Client
        httpx.Client = lambda *a, **k: orig_client(transport=transport)
        try:
            asyncio.run(handle_critical(None, _critical_res(), "industry", can_push=True, force=False, dry_run=False))
        finally:
            httpx.Client = orig_client
        assert len(calls) == 1
        assert store_mod.is_new_critical("crit-1") is False
    finally:
        store_mod.critical_alerts_path = orig_path


def test_critical_dry_run_no_send():
    tmp = Path(tempfile.mkdtemp())
    orig_path = store_mod.critical_alerts_path
    _patch_critical(tmp)
    try:
        from radar.cli import handle_critical
        calls = []
        def handler(req):
            calls.append(req)
            return httpx.Response(200, json={"code": 0})
        transport = httpx.MockTransport(handler)
        os.environ["LARK_WEBHOOK_INDUSTRY"] = "https://lark.example/hook"
        import outputs.lark as L
        orig_client = httpx.Client
        httpx.Client = lambda *a, **k: orig_client(transport=transport)
        try:
            asyncio.run(handle_critical(None, _critical_res(), "industry", can_push=True, force=False, dry_run=True))
        finally:
            httpx.Client = orig_client
        assert calls == []
    finally:
        store_mod.critical_alerts_path = orig_path
