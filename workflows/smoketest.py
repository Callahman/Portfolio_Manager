"""Smoke test (Epic 8) — verifies the working tree is runnable.

Checks (all must pass):
  1. every top-level package imports
  2. the read-only API app builds
  3. the dashboard app builds

Usage:
  python -m workflows.smoketest
Exit 0 = pass, 1 = fail (the failing check is named).
"""
from __future__ import annotations

import importlib
import logging
import sys

log = logging.getLogger(__name__)

PACKAGES = ["common", "collect", "validate", "analyze", "portfolio", "delivery", "api", "team", "workflows"]


def run() -> int:
    failures = []
    for pkg in PACKAGES:
        try:
            importlib.import_module(pkg)
            log.info("import ok: %s", pkg)
        except Exception as e:
            failures.append(f"import {pkg}: {e}")
    try:
        from api import server

        server.create_app()
        log.info("api app builds")
    except Exception as e:
        failures.append(f"api app: {e}")
    try:
        from delivery.dashboard import app as dash

        dash.create_app()
        log.info("dashboard app builds")
    except Exception as e:
        failures.append(f"dashboard app: {e}")
    if failures:
        for f in failures:
            log.error("FAIL %s", f)
        return 1
    log.info("smoke test PASS (%d checks)", len(PACKAGES) + 2)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(run())
