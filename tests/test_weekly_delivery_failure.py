"""A failed external weekly delivery must fail the scheduled job."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from outputs.base import DeliveryResult
from radar.cli import do_weekly


def test_weekly_lark_failure_is_not_green_ci():
    result = {
        "events": [], "critical_events": [], "sources_checked": 2, "sources_failed": 0,
    }
    settings = {"runtime": {"push": {"critical_enabled": False}}}
    failed_lark = DeliveryResult(target="lark", success=False, status="failed")
    with patch("radar.cli.run_radar", new=AsyncMock(return_value=result)), \
         patch("radar.cli.deliver_weekly", new=AsyncMock(return_value=(MagicMock(), [failed_lark]))), \
         patch("radar.cli.handle_critical", new=AsyncMock()), \
         patch("radar.cli.make_guard", return_value=MagicMock()), \
         patch("radar.cli.print_summary"):
        try:
            asyncio.run(do_weekly("industry", False, True, "lark", True, False,
                                  settings, MagicMock(), MagicMock()))
        except RuntimeError as exc:
            assert "external delivery failed for: industry/lark" in str(exc)
        else:
            raise AssertionError("weekly Lark failure must fail the job")
