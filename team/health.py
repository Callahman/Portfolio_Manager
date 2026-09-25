"""Team-runtime health endpoint (Epic 11.3) — a tiny HTTP server on the
4090 so the 1080's dashboard can check the 4090's reachability.

Usage:
  python -m team.health
"""
from __future__ import annotations

import json
import logging
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from common import config
from team import roles as team_roles

log = logging.getLogger(__name__)

LAST_SESSION = {"ts": None, "session_id": None, "status": None}


def record_session(session_id: str, status: str) -> None:
    LAST_SESSION.update(ts=time.time(), session_id=session_id, status=status)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/health", "/"):
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(
            {
                "status": "ok",
                "ts": time.time(),
                "defined_roles": team_roles.all_roles(),
                "last_session": LAST_SESSION,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.debug(fmt, *args)


def main() -> int:
    config.load_env()
    host = config.get("TEAM_HEALTH_HOST", "0.0.0.0") or "0.0.0.0"
    port = config.get_int("TEAM_HEALTH_PORT", 8500)
    log.info("team-runtime health on %s:%d", host, port)
    HTTPServer((host, port), _Handler).serve_forever()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
