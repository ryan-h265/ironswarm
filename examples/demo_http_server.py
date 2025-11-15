#!/usr/bin/env python3
"""Small demo HTTP server for ironswarm examples.

Run with:

    python examples/demo_http_server.py --port 8080

The server exposes a few endpoints with predictable yet non-trivial
behaviour so that scenario scripts can target them when experimenting
with ironswarm.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


class DemoRequestHandler(BaseHTTPRequestHandler):
    """Request handler implementing a couple of REST-like routes."""

    server_version = "IronswarmDemo/1.0"

    def _write_response(
        self,
        status: HTTPStatus,
        payload: Any,
        content_type: str = "application/json",
    ) -> None:
        body = payload
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            body = payload.encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _simulate_latency(self) -> None:
        """Sleep for a random duration to imitate real services."""
        max_delay = getattr(self.server, "max_delay", 0.25)
        time.sleep(random.uniform(0, max_delay))

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        routes: dict[str, Callable[[], None]] = {
            "/": self._handle_home,
            "/health": self._handle_health,
            "/api/items": self._handle_list_items,
            "/api/items/slow": self._handle_slow_items,
        }
        handler = routes.get(self.path)
        if handler:
            handler()
            return
        if self.path.startswith("/error/"):
            self._handle_error_endpoint()
            return
        self._handle_unknown()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/echo":
            self._write_response(
                HTTPStatus.OK,
                {
                    "message": "demo placeholder",
                    "path": self.path,
                    "note": "no-op endpoint",
                },
            )
            return
        content_length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(content_length) if content_length else b""
        try:
            data = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            data = {"raw": payload.decode("utf-8", errors="replace")}
        self._simulate_latency()
        self._write_response(HTTPStatus.CREATED, {"echo": data})

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        """Route logging through print so it is visible during demos."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {self.command} {self.path} - {fmt % args}")

    # Handlers -----------------------------------------------------------------

    def _handle_home(self) -> None:
        self._simulate_latency()
        html = """
        <html>
            <head><title>Ironswarm Demo</title></head>
            <body>
                <h1>Ironswarm Demo Service</h1>
                <p>Available routes:</p>
                <ul>
                    <li>GET /health</li>
                    <li>GET /api/items</li>
                    <li>GET /api/items/slow</li>
                    <li>POST /api/echo</li>
                    <li>GET /error/&lt;status&gt; (e.g. /error/503)</li>
                </ul>
            </body>
        </html>
        """.strip()
        self._write_response(HTTPStatus.OK, html, content_type="text/html; charset=utf-8")

    def _handle_health(self) -> None:
        self._write_response(HTTPStatus.OK, {"status": "ok", "timestamp": time.time()})

    def _handle_list_items(self) -> None:
        self._simulate_latency()
        items = [
            {"id": idx, "name": name, "price": round(random.uniform(5, 50), 2)}
            for idx, name in enumerate(["alpha", "beta", "gamma", "delta"], start=1)
        ]
        self._write_response(HTTPStatus.OK, {"items": items})

    def _handle_slow_items(self) -> None:
        delay = getattr(self.server, "slow_delay", 1.5)
        time.sleep(delay)
        self._write_response(HTTPStatus.OK, {"items": ["slow", "response"], "delay": delay})

    def _handle_error_endpoint(self) -> None:
        try:
            status_code = int(self.path.split("/", maxsplit=2)[-1])
            status = HTTPStatus(status_code)
        except (ValueError, KeyError):
            self._write_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid status code", "path": self.path},
            )
            return
        self._write_response(
            status,
            {
                "message": f"Simulated {status.value}",
                "status": status.value,
                "reason": status.phrase,
            },
        )

    def _handle_unknown(self) -> None:
        self._write_response(
            HTTPStatus.OK,
            {
                "message": "demo placeholder",
                "path": self.path,
                "available": ["/", "/health", "/api/items", "/api/items/slow", "/api/echo"],
            },
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simple demo HTTP server")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument(
        "--max-delay",
        type=float,
        default=0.25,
        help="Maximum random latency for fast endpoints (seconds, default: 0.25)",
    )
    parser.add_argument(
        "--slow-delay",
        type=float,
        default=1.5,
        help="Delay for /api/items/slow responses (seconds, default: 1.5)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DemoRequestHandler)
    server.max_delay = max(0.0, args.max_delay)
    server.slow_delay = max(0.0, args.slow_delay)
    print(f"Demo server listening on http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
