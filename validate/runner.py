"""Entry point for the systemd validate timer (1080).

Usage:
  python -m validate.runner

Runs the quality checks, writes cleaned/validated records to
warehouse/validated (its own schema), emits the data quality report and
structured failure reports.
"""
from __future__ import annotations

import logging
import sys

import pandas as pd

log = logging.getLogger(__name__)


def write_validated() -> None:
    """Cleaned/verified records + validation metadata into warehouse/validated."""
    from collect import raw_store
    from common import config

    vdir = config.VALIDATED_DIR
    for sub in ("prices", "macro", "news"):
        (vdir / sub).mkdir(parents=True, exist_ok=True)

    for t in raw_store.all_price_tickers():
        df = raw_store.load_price_series(t)
        if df.empty:
            continue
        df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        df.to_parquet(vdir / "prices" / f"{t}.parquet", index=False)

    for sid in raw_store.all_macro_series_ids():
        df = raw_store.load_macro_series(sid)
        if df.empty:
            continue
        df.to_parquet(vdir / "macro" / f"{sid}.parquet", index=False)

    for slug in raw_store.all_news_feeds():
        items = raw_store.load_news(slug)
        import json

        with (vdir / "news" / f"{slug}.jsonl").open("w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")


def main() -> int:
    from common import config
    from validate import failures as vfailures
    from validate import quality
    from validate.checks import run_checks

    config.load_env()
    write_validated()
    results = run_checks()
    open_ids = vfailures.emit_failure_reports(results)
    report = quality.build_report(results, open_ids)
    quality.write_report(report)

    s = report["summary"]
    log.info(
        "validate done: %d sources (%d ok, %d stale, %d failed); open failures: %s",
        s["total_sources"], s["ok"], s["stale"], s["failed"], open_ids or "none",
    )
    # exit non-zero only if EVERYTHING failed (a run with some stale data is still usable)
    return 0 if s["ok"] > 0 or s["total_sources"] == 0 else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main())
