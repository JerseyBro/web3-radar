from __future__ import annotations
import logging
from typing import Iterable

from outputs.base import BaseOutput, DeliveryResult, DeliveryContext
from outputs.file import FileOutput
from outputs.lark import LarkOutput
from outputs.local_http import LocalHTTPOutput

logger = logging.getLogger(__name__)


class OutputRouter:
    """Deliver a report to multiple targets. One target failing must not block others."""

    TARGETS = {
        "file": FileOutput,
        "lark": LarkOutput,
        "local-http": LocalHTTPOutput,
    }

    def __init__(self, targets: list[str], state=None, settings: dict | None = None):
        settings = settings or {}
        delivery_cfg = settings.get("delivery", {})
        self.outputs: list[BaseOutput] = []
        for t in targets:
            t = t.strip()
            if t not in self.TARGETS:
                logger.warning(f"[router] unknown target '{t}', skipping")
                continue
            self.outputs.append(self.TARGETS[t]())

    def deliver(self, report, context: DeliveryContext) -> list[DeliveryResult]:
        results: list[DeliveryResult] = []
        for out in self.outputs:
            try:
                res = out.deliver(report, context)
                results.append(res)
                if res.success:
                    logger.info(res.to_log())
                else:
                    logger.error(res.to_log())
            except Exception as e:
                logger.error(f"[router] {out.target} crashed: {e}")
                results.append(DeliveryResult(target=out.target, success=False, status="failed",
                                              error_type="UNKNOWN", error_message=str(e)))
        return results

    @staticmethod
    def parse(targets_str: str | None, default: list[str] | None = None) -> list[str]:
        if not targets_str:
            return default or ["file"]
        return [t.strip() for t in targets_str.split(",") if t.strip()]
