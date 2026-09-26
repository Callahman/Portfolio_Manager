"""Team-runtime health endpoint (Epic 11.3) — a tiny HTTP server on the
4090 so the 1080's dashboard can check the 4090's reachability.

Usage:
  python -m team.health
"""
from __future__ import annotations

import json
import logging
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from common import config
from team import roles as team_roles

log = logging.getLogger(__name__)

LAST_SESSION = {"ts": None, "session_id": None, "status": None}


def record_session(session_id: str, status: str) -> None:
    LAST_SESSION.update(ts=time.time(), session_id=session_id, status=status)


def lan_ip() -> str:
    """Determine this host's LAN IP (UDP connect trick; no data is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return ""
    finally:
        s.close()


def self_register(port: int) -> None:
    """Announce this team runtime to the 1080 (best-effort; never blocks).

    The 4090 is strictly ad-hoc (no schedule, no static IP), so it reports its
    own LAN IP to the 1080's POST /register on startup. A failed registration
    only logs — the health server still runs.
    """
    base = (config.get("FEED_API_BASE") or "").strip()
    if not base:
        log.info("FEED_API_BASE not set — skipping self-registration")
        return
    ip = lan_ip()
    if not ip:
        log.warning("could not determine LAN IP — skipping self-registration")
        return
    health_url = f"http://{ip}:{port}/health"
    try:
        import requests

        r = requests.post(f"{base}/register", json={"ip": ip, "health_url": health_url}, timeout=10)
        if r.ok:
            log.info("registered team runtime %s with 1080 (%s)", health_url, base)
        else:
            log.warning("self-registration failed: HTTP %d (%s)", r.status_code, r.text[:200])
    except Exception as e:  # noqa: BLE001
        log.warning("self-registration failed: %s", e)


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
    self_register(port)
    log.info("team-runtime health on %s:%d", host, port)
    HTTPServer((host, port), _Handler).serve_forever()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
