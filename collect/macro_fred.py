"""Macro fetcher — FRED public API (rates, CPI, unemployment, ...).

FRED requires a free API key (`FRED_API_KEY` in .env). A missing key is a
visible `config_missing` failure, never a silent skip.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

import pandas as pd
import requests

from common import config

log = logging.getLogger(__name__)

API = "https://api.stlouisfed.org/fred/series/observations"
TIMEOUT_S = 30


def with_retries(fn: Callable[[], pd.DataFrame], attempts: int = 3, backoff: float = 2.0) -> pd.DataFrame:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(backoff * (i + 1))
    assert last is not None
    raise last


def fetch_fred_series(series_id: str, api_key: str, limit: int | None = None) -> pd.DataFrame:
    """Observations for one FRED series. Columns: date, value."""
    params = {"series_id": series_id, "api_key": api_key, "file_type": "json", "sort_order": "asc"}
    if limit:
        params["limit"] = limit

    def _do() -> pd.DataFrame:
        r = requests.get(API, params=params, timeout=TIMEOUT_S)
        if r.status_code == 400:
            raise ValueError(f"FRED bad request for {series_id} (check FRED_API_KEY / series id)")
        r.raise_for_status()
        obs = r.json().get("observations") or []
        rows = [(o["date"], None if o["value"] == "." else o["value"]) for o in obs]
        df = pd.DataFrame(rows, columns=["date", "value"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df.dropna(subset=["value"])

    return with_retries(_do)


def run() -> int:
    """CLI entry: fetch all configured FRED series into warehouse/raw."""
    config.load_env()
    api_key = (config.get("FRED_API_KEY") or "").strip()
    series_ids = config.get_list("FRED_SERIES")
    if not api_key:
        from collect import raw_store

        raw_store.record_fetch("macro:fred:*", "macro", 0, "failed", "FRED_API_KEY not set (config_missing)")
        log.error("FRED_API_KEY not set — macro fetch failed visibly (config_missing)")
        return 1
    if not series_ids:
        log.error("FRED_SERIES is empty — nothing to fetch")
        return 1

    from collect import raw_store

    failed = 0
    for sid in series_ids:
        try:
            df = fetch_fred_series(sid, api_key)
            rows = raw_store.upsert_macro_series(sid, df)
            raw_store.record_fetch(f"macro:fred:{sid}", "macro", rows, "ok")
            log.info("macro fetch ok: %s (+ %d rows)", sid, rows)
        except Exception as e:  # noqa: BLE001
            failed += 1
            raw_store.record_fetch(f"macro:fred:{sid}", "macro", 0, "failed", str(e))
            log.warning("macro fetch FAILED for %s: %s", sid, e)
    return 1 if failed == len(series_ids) else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    raise SystemExit(run())
