from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from radar.config import ROOT

logger = logging.getLogger(__name__)
RECEIVER_DIR = ROOT / "storage" / "local-receiver"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": body}).encode())

    def do_GET(self):
        if urlparse(self.path).path == "/health":
            self._send(200, "ok")
            return
        self._send(404, "not found")

    def do_POST(self):
        if urlparse(self.path).path != "/api/radar":
            self._send(404, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw or b"{}")
        except Exception as e:
            self._send(400, f"bad request: {e}")
            return
        # Persist (no sensitive headers / tokens printed)
        RECEIVER_DIR.mkdir(parents=True, exist_ok=True)
        fname = datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"
        (RECEIVER_DIR / fname).open("a", encoding="utf-8").write(json.dumps(data, ensure_ascii=False) + "\n")
        # Console summary (safe fields only)
        radar = data.get("radar", "?")
        etype = data.get("event_type", "?")
        title = (data.get("report", {}) or {}).get("title", "")
        print(f"[{datetime.now(timezone.utc).isoformat()}] radar={radar} event_type={etype} title={title}")
        self._send(200, "received")

    def log_message(self, fmt, *args):
        # Avoid logging request lines that may contain tokens
        pass


def run_receiver(host: str = "127.0.0.1", port: int = 8787):
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Local debug receiver on http://{host}:{port} (GET /health, POST /api/radar)")
    print(f"Received data -> {RECEIVER_DIR}/YYYY-MM-DD.jsonl")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
