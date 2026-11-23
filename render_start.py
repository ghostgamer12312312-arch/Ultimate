"""Render entrypoint: keep a health port open, then run the Telegram bot."""

from __future__ import annotations

import os
import runpy
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"Rise of Legends is running.\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        return


def serve_health() -> None:
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    threading.Thread(target=serve_health, daemon=True).start()
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ultimate"))
    runpy.run_path(os.path.join(os.path.dirname(__file__), "ultimate", "main.py"), run_name="__main__")
