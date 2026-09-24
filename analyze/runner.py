"""Entry point for the systemd analyze timer (1080).

Usage:
  python -m analyze.runner

Builds all five analytics (snapshot, signals, fundamentals, macro, risk)
into warehouse/analytics (its own schema) + per-role feeds.
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def main() -> int:
    from common import config
    from analyze import feeds, fundamentals, macro, risk, signals, snapshot

    config.load_env()
    watchlist = config.get_list("WATCHLIST")
    series_ids = config.get_list("FRED_SERIES")
    if not watchlist:
        log.error("WATCHLIST is empty — cannot build analytics")
        return 1

    snap = snapshot.build(watchlist)
    sig = signals.build(watchlist)
    fund = fundamentals.build(watchlist)
    mac = macro.build(series_ids)
    rk = risk.build(watchlist)

    paths = [
        snapshot.write(snap),
        signals.write(sig),
        fundamentals.write(fund),
        macro.write(mac),
        risk.write(rk),
    ]
    for role in feeds.all_roles():
        feeds.write_feed(role)

    log.info(
        "analyze done: %d assets, %d macro series, %d roles; outputs: %s",
        len(snap["assets"]), len(mac["series"]), len(feeds.all_roles()),
        ", ".join(str(p.name) for p in paths),
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main())
