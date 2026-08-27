from __future__ import annotations
import hashlib
import hmac
import base64
import time
import json
import logging
import os
import httpx

from outputs.base import (
    BaseOutput, DeliveryResult, DeliveryContext, DeliveryStatus, DeliveryError,
)
from radar.report import Report

logger = logging.getLogger(__name__)

RETRY_MAX = 3
BACKOFF_BASE = 1.0
TIMEOUT = 15

# Lark business error code mapping
_CODE_MAP = {
    19001: DeliveryError.INVALID_WEBHOOK,
    19021: DeliveryError.KEYWORD_REJECTED,
    19022: DeliveryError.IP_REJECTED,
    19024: DeliveryError.SIGNATURE_ERROR,
    19020: DeliveryError.INVALID_PAYLOAD,
}


def _sign(secret: str, timestamp: str) -> str:
    # Feishu/Lark custom bot signature: HMAC-SHA256(key=secret, msg=f"{timestamp}\n{secret}")
    string_to_sign = f"{timestamp}\n{secret}"
    h = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256)
    return base64.b64encode(h.digest()).decode()


def build_industry_card(report_title: str, summary: str, events: list[dict]) -> dict:
    elements = []
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{report_title}**\n{summary[:400]}"}})
    if events:
        md = "\n".join([f"• [{e['title'][:60]}]({e['url']}) `score:{e.get('score','')}`" for e in events[:6]])
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**🔥 Top Signals**\n{md}"}})
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "💰 Money Flow / 🚀 Narrative / ⚙️ Technology / 💡 Opportunities 详见完整报告."}})
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "📡 Web3 Industry Intelligence"}, "template": "blue"},
            "elements": elements,
        },
    }


def build_competitor_card(report_title: str, summary: str, events: list[dict]) -> dict:
    elements = []
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{report_title}**\n{summary[:400]}"}})
    if events:
        md = "\n".join([f"• [{e['title'][:60]}]({e['url']}) `score:{e.get('score','')}`" for e in events[:6]])
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**🏆 Top Competitor Moves**\n{md}"}})
    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "🔄 Direction / ⚙️ Tech / 💡 Opportunities 详见完整报告."}})
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "👛 Web3 Wallet Competitor Intelligence"}, "template": "orange"},
            "elements": elements,
        },
    }


def build_card_from_report(report: Report) -> dict:
    if report.kind == "smoke":
        return build_smoke_card(report)
    top = [
        {"title": e.title, "url": e.source_url, "score": e.score}
        for e in report.events[:6]
    ]
    summary = report.markdown[:600]
    if report.radar == "competitor":
        return build_competitor_card(f"{report.kind.capitalize()} {report.period}", summary, top)
    return build_industry_card(f"{report.kind.capitalize()} {report.period}", summary, top)


def build_smoke_card(report: Report) -> dict:
    meta = report.meta or {}
    lines = [
        "**Web3 Intelligence Radar**",
        "Delivery Test",
        f"environment: {meta.get('environment','test')}",
        f"radar: {report.radar}",
        f"timestamp: {report.generated_at}",
        f"status: {meta.get('status','ok')}",
    ]
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "🧪 Radar Delivery Test"}, "template": "grey"},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}],
        },
    }


def send_lark(webhook: str, payload: dict, secret: str | None = None, dry_run: bool = False) -> dict:
    """Single-attempt delivery. Returns structured dict with ok/error_type."""
    if dry_run:
        logger.info("[DRY-RUN] Lark payload built (not sent).")
        return {"ok": True, "dry_run": True}
    if not webhook:
        return {"ok": False, "error_type": DeliveryError.INVALID_WEBHOOK.value, "error_message": "no webhook"}
    try:
        url = webhook
        if secret:
            ts = str(int(time.time()))
            sign = _sign(secret, ts)
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}timestamp={ts}&sign={sign}"
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(url, json=payload)
            try:
                j = resp.json()
            except Exception:
                j = {}
            if resp.status_code != 200:
                return {"ok": False, "error_type": DeliveryError.NETWORK_ERROR.value,
                        "error_message": f"HTTP {resp.status_code}"}
            code = j.get("code", 0)
            if code == 0:
                return {"ok": True}
            msg = (j.get("msg") or "").lower()
            if code in _CODE_MAP:
                et = _CODE_MAP[code].value
            elif "rate" in msg or code == 99999:
                et = DeliveryError.RATE_LIMIT.value
            else:
                et = DeliveryError.UNKNOWN.value
            return {"ok": False, "error_type": et, "error_message": j.get("msg")}
    except httpx.TimeoutException:
        return {"ok": False, "error_type": DeliveryError.TIMEOUT.value, "error_message": "request timeout"}
    except httpx.HTTPError as e:
        return {"ok": False, "error_type": DeliveryError.NETWORK_ERROR.value, "error_message": str(e)}
    except Exception as e:
        return {"ok": False, "error_type": DeliveryError.UNKNOWN.value, "error_message": str(e)}


class LarkOutput(BaseOutput):
    target = "lark"

    def __init__(self, retry_max: int = RETRY_MAX, backoff_base: float = BACKOFF_BASE):
        self.retry_max = retry_max
        self.backoff_base = backoff_base

    def deliver(self, report: Report, context: DeliveryContext) -> DeliveryResult:
        radar = context.radar
        webhook = os.getenv(f"LARK_WEBHOOK_{radar.upper()}")
        secret = os.getenv(f"LARK_SIGNING_SECRET_{radar.upper()}")

        if context.dry_run:
            return DeliveryResult(target=self.target, success=True, status=DeliveryStatus.PREVIEW.value, attempts=0)

        if not webhook:
            return DeliveryResult(target=self.target, success=False,
                                  status=DeliveryStatus.FAILED.value,
                                  error_type=DeliveryError.INVALID_WEBHOOK.value,
                                  error_message="LARK_WEBHOOK_{radar} not set")

        # idempotency
        if context.state is not None and not context.force:
            if context.state.already_delivered(self.target, context.report_id):
                return DeliveryResult(target=self.target, success=True,
                                      status=DeliveryStatus.SKIPPED.value, attempts=0,
                                      detail={"reason": "already delivered"})

        payload = build_card_from_report(report)
        attempts = 0
        last_err_type = DeliveryError.UNKNOWN.value
        last_err_msg = ""
        start = time.monotonic()
        for attempt in range(self.retry_max):
            attempts += 1
            res = send_lark(webhook, payload, secret)
            if res.get("ok"):
                if context.state is not None:
                    context.state.record_delivery(self.target, context.report_id, "ok")
                return DeliveryResult(target=self.target, success=True,
                                      status=DeliveryStatus.SUCCESS.value, attempts=attempts,
                                      duration_ms=int((time.monotonic()-start)*1000))
            last_err_type = res.get("error_type", DeliveryError.UNKNOWN.value)
            last_err_msg = res.get("error_message", "")
            # Do not retry on deterministic failures that won't recover
            if last_err_type in (DeliveryError.INVALID_WEBHOOK.value,
                                 DeliveryError.SIGNATURE_ERROR.value,
                                 DeliveryError.KEYWORD_REJECTED.value,
                                 DeliveryError.IP_REJECTED.value):
                break
            time.sleep(self.backoff_base * (2 ** attempt))
        return DeliveryResult(target=self.target, success=False,
                              status=DeliveryStatus.FAILED.value,
                              error_type=last_err_type, error_message=last_err_msg,
                              attempts=attempts,
                              duration_ms=int((time.monotonic()-start)*1000))
