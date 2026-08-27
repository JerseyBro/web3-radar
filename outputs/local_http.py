from __future__ import annotations
import os
import time
import uuid
import logging

import httpx

from outputs.base import (
    BaseOutput, DeliveryResult, DeliveryContext, DeliveryStatus, DeliveryError,
)
from radar.report import Report

logger = logging.getLogger(__name__)

RETRY_MAX = 3
BACKOFF_BASE = 1.0
TIMEOUT = 15


class LocalHTTPOutput(BaseOutput):
    target = "local-http"

    def __init__(self, retry_max: int = RETRY_MAX, backoff_base: float = BACKOFF_BASE):
        self.retry_max = retry_max
        self.backoff_base = backoff_base

    def _envelope(self, report: Report, context: DeliveryContext) -> dict:
        return {
            "schema_version": "1",
            "event_type": "weekly_report" if report.kind == "weekly" else report.kind,
            "radar": report.radar,
            "generated_at": report.generated_at,
            "report": {
                "report_id": report.id,
                "period": report.period,
                "title": report.title,
                "markdown": report.markdown,
                "events": [
                    {"event_id": e.event_id, "title": e.title,
                     "source": e.source, "source_url": e.source_url,
                     "score": e.score, "tier": e.tier}
                    for e in report.events[:50]
                ],
            },
            "meta": {
                "run_id": report.meta.get("run_id", str(uuid.uuid4())),
                "event_count": len(report.events),
                "ai_cost_usd": report.meta.get("ai_cost_usd", 0.0),
            },
        }

    def deliver(self, report: Report, context: DeliveryContext) -> DeliveryResult:
        url = os.getenv("LOCAL_WEBHOOK_URL")
        token = os.getenv("LOCAL_WEBHOOK_TOKEN")

        if context.dry_run:
            return DeliveryResult(target=self.target, success=True, status=DeliveryStatus.PREVIEW.value, attempts=0)

        if not url:
            return DeliveryResult(target=self.target, success=False,
                                  status=DeliveryStatus.FAILED.value,
                                  error_type=DeliveryError.INVALID_WEBHOOK.value,
                                  error_message="LOCAL_WEBHOOK_URL not set")

        if context.state is not None and not context.force:
            if context.state.already_delivered(self.target, context.report_id):
                return DeliveryResult(target=self.target, success=True,
                                      status=DeliveryStatus.SKIPPED.value, attempts=0,
                                      detail={"reason": "already delivered"})

        payload = self._envelope(report, context)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        attempts = 0
        last_err_type = DeliveryError.UNKNOWN.value
        last_err_msg = ""
        start = time.monotonic()
        for attempt in range(self.retry_max):
            attempts += 1
            try:
                with httpx.Client(timeout=TIMEOUT) as client:
                    resp = client.post(url, json=payload, headers=headers)
                if 200 <= resp.status_code < 300:
                    if context.state is not None:
                        context.state.record_delivery(self.target, context.report_id, "ok")
                    return DeliveryResult(target=self.target, success=True,
                                          status=DeliveryStatus.SUCCESS.value, attempts=attempts,
                                          duration_ms=int((time.monotonic()-start)*1000))
                if resp.status_code == 429:
                    last_err_type = DeliveryError.RATE_LIMIT.value
                elif resp.status_code >= 500:
                    last_err_type = DeliveryError.NETWORK_ERROR.value
                else:
                    last_err_type = DeliveryError.INVALID_PAYLOAD.value
                last_err_msg = f"HTTP {resp.status_code}"
            except httpx.TimeoutException:
                last_err_type = DeliveryError.TIMEOUT.value
                last_err_msg = "timeout"
            except httpx.HTTPError as e:
                last_err_type = DeliveryError.NETWORK_ERROR.value
                last_err_msg = str(e)
            # retry transient
            if last_err_type in (DeliveryError.TIMEOUT.value, DeliveryError.NETWORK_ERROR.value, DeliveryError.RATE_LIMIT.value):
                time.sleep(self.backoff_base * (2 ** attempt))
            else:
                break
        return DeliveryResult(target=self.target, success=False, status=DeliveryStatus.FAILED.value,
                              error_type=last_err_type, error_message=last_err_msg, attempts=attempts,
                              duration_ms=int((time.monotonic()-start)*1000))
