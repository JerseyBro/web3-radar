from __future__ import annotations
import hashlib
import hmac
import base64
import time
import json
import logging
import httpx

logger = logging.getLogger(__name__)

def _sign(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    # Lark signing: HMAC-SHA256
    hm = hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256)
    # Actually spec: hmac with secret as key, string_to_sign as message? Check docs: timestamp + "\n" + secret as key?
    # Lark doc: sign = base64(HMAC-SHA256(timestamp + "\n" + secret, ""))
    # We'll implement both common variants: try standard
    # Use secret as key? Let's follow feishu: encrypt key is secret, message is timestamp\nsecret
    # We'll implement simple: hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    hm2 = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256)
    return base64.b64encode(hm2.digest()).decode()

def build_industry_card(report_title: str, summary: str, events: list[dict]) -> dict:
    # events: {title, url, score}
    elements = []
    elements.append({"tag":"div","text":{"tag":"lark_md","content": f"**{report_title}**\n{summary[:400]}"}})
    if events:
        md = "\n".join([f"• [{e['title'][:60]}]({e['url']}) `score:{e.get('score','')}`" for e in events[:6]])
        elements.append({"tag":"div","text":{"tag":"lark_md","content": f"**🔥 Top Signals**\n{md}"}})
    # add sections placeholder
    elements.append({"tag":"div","text":{"tag":"lark_md","content": "💰 Money Flow / 🚀 Narrative / ⚙️ Technology / 💡 Opportunities 详见完整报告."}})
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag":"plain_text","content":"📡 Web3 Industry Intelligence"}, "template":"blue"},
            "elements": elements
        }
    }

def build_competitor_card(report_title: str, summary: str, events: list[dict]) -> dict:
    elements = []
    elements.append({"tag":"div","text":{"tag":"lark_md","content": f"**{report_title}**\n{summary[:400]}"}})
    if events:
        md = "\n".join([f"• [{e['title'][:60]}]({e['url']}) `score:{e.get('score','')}`" for e in events[:6]])
        elements.append({"tag":"div","text":{"tag":"lark_md","content": f"**🏆 Top Competitor Moves**\n{md}"}})
    elements.append({"tag":"div","text":{"tag":"lark_md","content": "🔄 Direction / ⚙️ Tech / 💡 Opportunities 详见完整报告."}})
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag":"plain_text","content":"👛 Web3 Wallet Competitor Intelligence"}, "template":"orange"},
            "elements": elements
        }
    }

def send_lark(webhook: str, payload: dict, secret: str | None = None, dry_run: bool = False) -> dict:
    if dry_run:
        logger.info(f"[DRY-RUN] Lark payload: {json.dumps(payload, ensure_ascii=False)[:1000]}")
        return {"dry_run": True, "payload": payload}
    if not webhook:
        return {"error":"no webhook"}
    try:
        # signing if secret provided (query params)
        url = webhook
        if secret:
            ts = str(int(time.time()))
            sign = _sign(secret, ts)
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}timestamp={ts}&sign={sign}"
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, json=payload)
            try:
                j = resp.json()
            except:
                j = {"status_code": resp.status_code, "text": resp.text[:500]}
            return j
    except Exception as e:
        logger.error(f"Lark send failed: {e}")
        return {"error": str(e)}
