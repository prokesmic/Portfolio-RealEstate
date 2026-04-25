from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_portfolio_snapshot import (
    OUTPUT_JS_PATH,
    OUTPUT_PATH,
    build_snapshot_payload,
    save_json,
    save_snapshot_js,
)


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_target_path(self) -> bool:
        return urlparse(self.path).path == "/api/refresh-portfolio"

    def do_GET(self) -> None:
        if not self._is_target_path():
            self._send_json(404, {"ok": False, "error": "Not found"})
            return
        self._send_json(
            200,
            {"ok": True, "message": "Send a POST request to refresh the portfolio snapshot."},
        )

    def do_POST(self) -> None:
        if not self._is_target_path():
            self._send_json(404, {"ok": False, "error": "Not found"})
            return

        try:
            payload = build_snapshot_payload(output_path=OUTPUT_PATH)
            save_json(OUTPUT_PATH, payload)
            save_snapshot_js(OUTPUT_JS_PATH, payload)
        except Exception as exc:
            self._send_json(
                500,
                {
                    "ok": False,
                    "error": "Failed to rebuild the portfolio snapshot.",
                    "detail": str(exc),
                },
            )
            return

        self._send_json(
            200,
            {
                "ok": True,
                "generated_at": payload.get("generated_at"),
                "property_count": len(payload.get("properties", [])),
                "snapshot": payload,
            },
        )

    def log_message(self, format: str, *args) -> None:
        return
