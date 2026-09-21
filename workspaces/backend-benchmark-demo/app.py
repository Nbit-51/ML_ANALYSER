"""Tiny deterministic HTTP backend used by the benchmark adapter demo."""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config() -> dict[str, int | float]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - method name is defined by BaseHTTPRequestHandler
        if self.path == "/health":
            self._respond({"status": "ok"})
            return
        if self.path == "/benchmark":
            config = load_config()
            time.sleep(float(config["delay_seconds"]))
            count = int(config["items"])
            self._respond({"count": count, "items": list(range(count))})
            return
        self.send_error(404)

    def _respond(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    arguments = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), DemoHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
