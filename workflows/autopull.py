"""Auto-pull (Epic 8) — the 1080 pulls the 4090's commits on a timer,
smoke-tests them, and reverts to the last known-good if the smoke test
fails.

Flow:
  1. record current HEAD
  2. git pull --ff-only
  3. if HEAD changed: run the smoke test (imports every package + builds
     both FastAPI apps)
  4. smoke failure -> git reset --hard <old HEAD> (revert to last
     known-good), move the last-known-good tag, and email an alert
  5. smoke pass -> move the last-known-good tag to the new commit, restart
     the long-running services, and verify the API health
  6. post-restart health failure -> revert to the last known-good, restart
     again, and email an alert

The last known-good commit is tracked as a moving git tag
(``last-known-good``) so a revert always has a precise target.

Usage:
  python -m workflows.autopull
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

import requests

from common import config

log = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent

LAST_KNOWN_GOOD_TAG = "last-known-good"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=300
    )


def _head() -> str:
    return _git("rev-parse", "HEAD").stdout.strip()


def _smoke(timeout: int = 300) -> bool:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "workflows.smoketest"],
            cwd=REPO, capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        log.error("smoke test timed out after %ds", timeout)
        return False


def _tag_last_known_good(head: str) -> None:
    r = _git("tag", "-f", LAST_KNOWN_GOOD_TAG, head)
    if r.returncode != 0:
        log.warning("could not move %s tag: %s", LAST_KNOWN_GOOD_TAG, r.stderr.strip()[:200])


def _services_to_restart() -> list[str]:
    raw = (config.get("SERVICES_TO_RESTART") or "pm-api").strip()
    return [s.strip() for s in raw.split(",") if s.strip()]


def _restart_services(services: list[str]) -> bool:
    if not services:
        return True
    try:
        r = subprocess.run(
            ["systemctl", "restart", *services],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            log.warning("systemctl restart failed: %s", r.stderr.strip()[:300])
            return False
        log.info("restarted services: %s", ", ".join(services))
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("could not restart services (%s): %s", ", ".join(services), e)
        return False


def _api_healthy(retries: int = 6, delay: float = 2.0) -> bool:
    port = config.get_int("API_PORT", 8400)
    url = f"http://127.0.0.1:{port}/health"
    for _ in range(retries):
        try:
            r = requests.get(url, timeout=5)
            if r.ok:
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def _alert(subject: str, body: str) -> None:
    try:
        from delivery import email as demail

        demail.send(subject, body)
    except Exception as e:
        log.warning("could not send alert email: %s", e)


def run() -> int:
    config.load_env()
    old = _head()
    pull = _git("pull", "--ff-only")
    if pull.returncode != 0:
        log.error("git pull failed: %s", pull.stderr.strip()[:500])
        return 1
    new = _head()
    if new == old:
        log.info("no new commits")
        return 0
    log.info("new commit: %s -> %s", old[:8], new[:8])
    if not _smoke():
        log.error("smoke test FAILED on new commit %s — reverting to %s", new[:8], old[:8])
        _git("reset", "--hard", old)
        _tag_last_known_good(old)
        _alert(
            "auto-pull: smoke test failed, reverted",
            f"The new commit {new[:12]} failed the smoke test and was reverted "
            f"to the last known-good {old[:12]}.",
        )
        return 1
    log.info("smoke test passed — keeping %s", new[:8])
    _tag_last_known_good(new)
    services = _services_to_restart()
    if services and _restart_services(services):
        if not _api_healthy():
            log.error("post-restart API health check FAILED — reverting to %s", old[:8])
            _git("reset", "--hard", old)
            _tag_last_known_good(old)
            _restart_services(services)
            _alert(
                "auto-pull: post-restart health failure, reverted",
                f"After restarting, the API health check failed. Reverted to the "
                f"last known-good {old[:12]} and restarted the services.",
            )
            return 1
    elif services:
        log.warning("service restart did not complete; running services unchanged")
    log.info("auto-pull complete: %s is now the last known-good", new[:8])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(run())
