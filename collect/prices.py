"""Price fetcher — free equity prices for the configurable watchlist.

Primary source: Yahoo Finance (unofficial chart API — needs a browser-like
User-Agent). Fallback source: stooq (daily CSV). Each fetch is retried
(bounded) and any unrecovered failure is reported with a visible status —
never silently skipped (outline §4.4).
"""
from __future__ import annotations

import logging
import time
from io import StringIO
from typing import Callable

import pandas as pd
import requests

from common import config

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT_S = 30


def with_retries(fn: Callable[[], pd.DataFrame], attempts: int = 3, backoff: float = 2.0) -> pd.DataFrame:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — fetchers must not kill the run
            last = e
            if i < attempts - 1:
                time.sleep(backoff * (i + 1))
    assert last is not None
    raise last


# ----------------------------------------------------------------- yahoo ---

def fetch_yahoo(ticker: str, range_: str = "1mo", interval: str = "1d") -> pd.DataFrame:
    """Daily OHLCV from Yahoo's chart API. Columns: date, open, high, low, close, volume."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {"range": range_, "interval": interval}

    def _do() -> pd.DataFrame:
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
        result = (data.get("chart", {}).get("result") or [None])[0]
        if result is None:
            err = (data.get("chart", {}).get("error") or {}).get("description", "no result")
            raise ValueError(f"yahoo chart error for {ticker}: {err}")
        ts = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(ts, unit="s"),
                "open": quote.get("open"),
                "high": quote.get("high"),
                "low": quote.get("low"),
                "close": quote.get("close"),
                "volume": quote.get("volume"),
            }
        )
        df = df.dropna(subset=["close"])
        return df

    return with_retries(_do)


# ----------------------------------------------------------------- stooq ---

def fetch_stooq(ticker: str) -> pd.DataFrame:
    """Daily OHLCV from stooq (full history CSV, tail 400 rows)."""
    sym = ticker.lower()
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"

    def _do() -> pd.DataFrame:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT_S)
        r.raise_for_status()
        text = r.text.strip()
        if not text or text.lower().startswith("no data"):
            raise ValueError(f"stooq returned no data for {ticker}")
        df = pd.read_csv(StringIO(text))
        df.columns = [c.lower() for c in df.columns]
        keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in df.columns]
        df = df[keep]
        df["date"] = pd.to_datetime(df["date"])
        return df.tail(400).reset_index(drop=True)

    return with_retries(_do)


# --------------------------------------------------------------- watchlist ---

def fetch_watchlist(tickers: list[str], source: str = "auto", range_: str = "1mo") -> dict[str, dict]:
    """Fetch the whole watchlist. Returns {ticker: {df, status, error, source}}."""
    out: dict[str, dict] = {}
    for t in tickers:
        df, error, used = None, "", source
        if source in ("auto", "yahoo"):
            try:
                df = fetch_yahoo(t, range_)
                used = "yahoo"
            except Exception as e:  # noqa: BLE001
                error = f"yahoo: {e}"
                if source == "yahoo":
                    df = None
        if df is None and source in ("auto", "stooq"):
            try:
                df = fetch_stooq(t)
                used = "stooq"
                error = ""
            except Exception as e:  # noqa: BLE001
                error = f"{error}; stooq: {e}" if error else f"stooq: {e}"
        out[t] = {
            "df": df,
            "status": "ok" if df is not None else "failed",
            "error": error,
            "source": used if df is not None else "none",
        }
    return out


def run() -> int:
    """CLI entry: fetch the watchlist into warehouse/raw. Returns exit code."""
    config.load_env()
    tickers = config.get_list("WATCHLIST")
    source = config.get("PRICE_SOURCE", "auto") or "auto"
    range_ = config.get("PRICE_HISTORY_RANGE", "1mo") or "1mo"
    if not tickers:
        log.error("WATCHLIST is empty — nothing to fetch")
        return 1

    from collect import raw_store

    results = fetch_watchlist(tickers, source=source, range_=range_)
    failed = 0
    for t, r in results.items():
        rows = raw_store.upsert_price_series(t, r["df"]) if r["df"] is not None else 0
        src = f"prices:{r['source']}:{t}" if r["df"] is not None else f"prices:fetch:{t}"
        raw_store.record_fetch(src, "prices", rows, r["status"], r["error"])
        if r["status"] == "failed":
            failed += 1
            log.warning("price fetch FAILED for %s: %s", t, r["error"])
        else:
            log.info("price fetch ok: %s (%s, + %d rows)", t, r["source"], rows)
    return 1 if failed == len(tickers) else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    raise SystemExit(run())
