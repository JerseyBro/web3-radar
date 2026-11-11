from __future__ import annotations
import hashlib
import hmac
import base64
import time
import json
import logging
import os
import re
from urllib.parse import urlsplit
import httpx

from outputs.base import (
    BaseOutput, DeliveryResult, DeliveryContext, DeliveryStatus, DeliveryError,
)
from radar.report import Report, public_source_url, redact_access_urls, verification_for_event

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


_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+.!<>|])")


def _safe_text(value: object, limit: int) -> str:
    """Render untrusted source text as one line of Lark Markdown text."""
    line = " ".join(redact_access_urls(value).split())[:limit]
    return _MD_SPECIAL.sub(r"\\\1", line)


def _safe_url(value: object) -> str | None:
    """Only include clickable links that cannot break Lark Markdown syntax."""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    if public_source_url(value) is None:
        return None
    if any(ord(ch) < 32 or ch.isspace() or ch in r"\\()[]<>\"'" for ch in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
    except ValueError:
        return None
    return value


def _div(content: str) -> dict:
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def _brief_card(
    radar: str,
    report_title: str,
    summary: str,
    events: list[dict],
    *,
    meta: dict | None = None,
) -> dict:
    meta = meta or {}
    checked = meta.get("sources_checked")
    failed = meta.get("sources_failed")
    candidate_only = meta.get("candidate_only") is True
    available = max(0, checked - failed) if isinstance(checked, int) and isinstance(failed, int) else None
    status = []
    if available is not None:
        status.append(f"来源可用 {available}/{checked}")
    status.append(f"待验证候选 {len(events)} 条" if candidate_only else f"入选 {len(events)} 条")
    cached = meta.get("cached_events_added")
    if isinstance(cached, int) and cached > 0:
        status.append(f"此前扫描补入 {cached} 条")
    mode = meta.get("analysis_mode")
    if mode in ("ai", "llm", "AI"):
        status.append("AI 辅助")
    elif mode in ("rules", "deterministic", "no_ai"):
        status.append("规则筛选")

    elements = [_div(f"**{_safe_text(report_title, 100)}**\n{' · '.join(status)}")]
    if isinstance(failed, int) and failed > 0:
        elements.append(_div(f"⚠️ {failed} 个来源失败，本次只覆盖可用来源。"))
    if summary:
        elements.append(_div(_safe_text(summary, 240)))

    shown = 0
    hidden = 0
    for event in events:
        if shown >= 3:
            break
        url = _safe_url(event.get("url"))
        if not url:
            hidden += 1
            continue
        shown += 1
        title = _safe_text(event.get("title") or "未命名信号", 100)
        source = _safe_text(event.get("source") or urlsplit(url).hostname, 60)
        date = _safe_text(event.get("published_at"), 24)
        label = "待验证 · " if candidate_only else ""
        lines = [f"**{shown}. {label}[{title}]({url})**"]
        detail = _safe_text(event.get("summary"), 160)
        if detail:
            lines.append(detail)
        implication = _safe_text(event.get("why"), 120)
        if implication:
            lines.append(f"可能影响：{implication}")
        action = _safe_text(event.get("action"), 140)
        if action:
            label = "AI 建议验证（待核查）" if event.get("ai_action") else "下一步验证"
            lines.append(f"{label}：{action}")
        lines.append(f"来源：[{source}]({url})" + (f" · {date}" if date else ""))
        elements.append(_div("\n".join(lines)))
    if not events:
        elements.append(_div("本次筛选无达标新信号；这不表示市场没有变化。"))
    elif not shown:
        subject = "候选" if candidate_only else "入选信号"
        elements.append(_div(f"{subject}的来源链接未通过校验，本消息未展示这些{subject}。"))
    elif hidden:
        subject = "候选" if candidate_only else "信号"
        elements.append(_div(f"另有 {hidden} 条{subject}因来源链接未通过校验而未展示。"))

    report_url = _safe_url(meta.get("report_url"))
    if report_url:
        elements.append(_div(f"[打开运行记录并下载完整报告]({report_url})"))
    industry = radar != "competitor"
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "📡 Web3 Industry Intelligence" if industry else "👛 Web3 Wallet Competitor Intelligence"},
                "template": "blue" if industry else "orange",
            },
            "elements": elements,
        },
    }


def build_industry_card(report_title: str, summary: str, events: list[dict]) -> dict:
    """Compatibility entry point for callers supplying simple event dicts."""
    return _brief_card("industry", report_title, summary, events)


def build_competitor_card(report_title: str, summary: str, events: list[dict]) -> dict:
    """Compatibility entry point for callers supplying simple event dicts."""
    return _brief_card("competitor", report_title, summary, events)


def build_card_from_report(report: Report) -> dict:
    if report.kind == "smoke":
        return build_smoke_card(report)
    events = [{
        "title": e.title,
        "url": e.source_url,
        "source": e.source,
        "summary": e.excerpt,
        "why": e.why_it_matters,
        "published_at": e.published_at.date().isoformat() if e.published_at else None,
        "action": e.developer_action or verification_for_event(e)[1],
        "ai_action": bool(e.developer_action),
    } for e in report.events]
    kind = "重点提醒" if report.kind == "critical" else "周报简报"
    return _brief_card(
        report.radar, f"{report.period} · {kind}", "", events,
        meta=report.meta,
    )


def build_smoke_card(report: Report) -> dict:
    meta = report.meta or {}
    lines = [
        "📡 Web3 Intelligence Radar",
        "Delivery Test",
        f"Radar: {report.radar.capitalize()}",
        f"Environment: {meta.get('environment', 'Production')}",
        "Status: Delivery channel works",
        f"Timestamp: {report.generated_at}",
    ]
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "📡 Web3 Intelligence Radar"}, "template": "grey"},
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
