"""Maintenance (Epic 11, Story 11.2) — archive caps, history pruning, log
rotation. Runs daily on the 1080 (pm-maintenance.timer).

  1. archives: delete the oldest daily archives beyond ARCHIVE_CAP_GB
  2. history: prune sessions to the rolling window (30) / cap (500 MB)
  3. pipeline logs: rotate history/pipeline/*.log over 5 MB (keep 3)

Usage:
  python -m workflows.maintenance
"""
from __future__ import annotations

import logging
import shutil
import sys

from common import config

log = logging.getLogger(__name__)

LOG_ROTATE_BYTES = 5 * 1024 * 1024
LOG_KEPT = 3


def _archive_cap() -> int:
    cap_gb = config.get_float("ARCHIVE_CAP_GB", 20.0)
    root = config.ARCHIVES_DIR
    if not root.is_dir():
        return 0
    days = sorted([d for d in root.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime)

    def total_gb() -> float:
        tot = 0
        for d in root.iterdir():
            if d.is_dir():
                for f in d.rglob("*"):
                    if f.is_file():
                        tot += f.stat().st_size
        return tot / (1024**3)

    deleted = 0
    for d in days:
        if total_gb() <= cap_gb:
            break
        shutil.rmtree(d)
        deleted += 1
        log.info("archive cap: deleted %s", d.name)
    return deleted


def _log_rotation() -> int:
    deleted = 0
    pdir = config.HISTORY_DIR / "pipeline"
    if not pdir.is_dir():
        return 0
    for logf in pdir.glob("*.log"):
        if logf.stat().st_size <= LOG_ROTATE_BYTES:
            continue
        for gen in range(LOG_KEPT - 1, 0, -1):
            src = pdir / f"{logf.name}.{gen}"
            if src.exists():
                src.rename(pdir / f"{logf.name}.{gen + 1}")
        logf.rename(pdir / f"{logf.name}.1")
        deleted += 1
    return deleted


def run() -> int:
    config.load_env()
    from common import history as chist

    a = _archive_cap()
    h = chist.prune()
    l = _log_rotation()
    log.info(
        "maintenance done: archives deleted=%d, history files deleted=%d, logs rotated=%d",
        a, h, l,
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(run())
