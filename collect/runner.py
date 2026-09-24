"""Entry point for the systemd collect timers (1080).

Usage:
  python -m collect.runner prices | macro | news | all
"""
from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


def main(argv: list[str]) -> int:
    which = argv[0] if argv else "all"
    from collect import macro_fred, news_rss, prices

    rc = 0
    if which in ("prices", "all"):
        rc |= prices.run()
    if which in ("macro", "all"):
        rc |= macro_fred.run()
    if which in ("news", "all"):
        rc |= news_rss.run()
    return rc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main(sys.argv[1:]))
