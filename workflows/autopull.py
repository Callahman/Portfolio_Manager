"""Auto-pull (Epic 8) — the 1080 pulls the 4090's code from the private
remote, smoke-tests it, and auto-reverts on failure.

Flow:
  1. record the current HEAD
  2. git pull --ff-only
  3. if HEAD changed: run the smoke test (workflows.smoketest)
  4. on smoke failure: git reset --hard <old HEAD> (auto-revert)
  5. on success: record the new HEAD

Usage:
  python -m workflows.autopull [--remote NAME] [--branch NAME]
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr[:500]}")
    return r.stdout.strip()


def _smoke() -> bool:
    r = subprocess.run(
        [sys.executable, "-m", "workflows.smoketest"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        log.error("smoke test failed:\n%s", (r.stdout + r.stderr)[-2000:])
        return False
    return True


def run(remote: str | None = None, branch: str | None = None) -> int:
    try:
        old_head = _git("rev-parse", "HEAD")
        args = ["pull", "--ff-only"]
        if remote:
            args.append(remote)
        if branch:
            args.append(branch)
        _git(*args)
        new_head = _git("rev-parse", "HEAD")
    except RuntimeError as e:
        log.error("pull failed: %s", e)
        return 1
    if new_head == old_head:
        log.info("pull ok — no new commits (%s)", new_head[:12])
        return 0
    log.info("new commits: %s -> %s", old_head[:12], new_head[:12])
    if not _smoke():
        log.error("auto-reverting to %s", old_head[:12])
        try:
            _git("reset", "--hard", old_head)
            log.info("reverted to %s", old_head[:12])
        except RuntimeError as e:
            log.error("REVERT FAILED — manual intervention needed: %s", e)
            return 1
        return 1
    log.info("autopull ok — running %s", new_head[:12])
    return 0


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    remote = None
    branch = None
    i = 1
    while i < len(argv):
        if argv[i] == "--remote":
            remote = argv[i + 1]
            i += 2
        elif argv[i] == "--branch":
            branch = argv[i + 1]
            i += 2
        else:
            log.error("unknown argument: %s", argv[i])
            return 1
    return run(remote=remote, branch=branch)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
