"""Deterministic quality checks per source (Step 2).

Checks: completeness (rows present), staleness (latest observation vs
today), schema (expected columns). Each check returns a per-source result
dict consumed by quality.py (report) and failures.py (failure reports).

Staleness rules (the 1080 is woken on a schedule, so some slack is normal):
  prices: latest_date within 4 days (weekends/holidays + wake cadence)
  macro:  latest_date within 3x the series' median observation gap
  news:   latest item within 26 hours
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from common import config
from collect import raw_store

PRICE_EXPECTED_COLS = {"date", "open", "high", "low", "close", "volume"}
MACRO_EXPECTED_COLS = {"date", "value"}

PRICES_STALE_DAYS = 4
NEWS_STALE_HOURS = 26


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_prices(watchlist: list[str]) -> list[dict]:
    out = []
    today = _today()
    for t in watchlist:
        df = raw_store.load_price_series(t)
        res = {
            "source": f"prices:{t}",
            "kind": "prices",
            "rows": 0,
            "latest": None,
            "fresh": False,
            "schema_ok": False,
            "status": "ok",
            "error": "",
        }
        if df.empty:
            res["status"] = "failed"
            res["error"] = "missing_data: no price series in warehouse/raw"
        else:
            res["rows"] = int(len(df))
            res["latest"] = str(df["date"].iloc[-1])
            res["schema_ok"] = PRICE_EXPECTED_COLS.issubset(set(df.columns))
            null_close = int(df["close"].isna().sum())
            if null_close:
                res["error"] = f"schema_mismatch: {null_close} null close values"
                res["status"] = "failed"
            else:
                gap = (pd.to_datetime(today) - pd.to_datetime(res["latest"])).days
                if gap > PRICES_STALE_DAYS:
                    res["fresh"] = False
                    res["status"] = "stale"
                    res["error"] = f"stale_data: latest price {gap} days old"
                else:
                    res["fresh"] = True
        out.append(res)
    return out


def check_macro(series_ids: list[str]) -> list[dict]:
    out = []
    today = pd.to_datetime(_today())
    for sid in series_ids:
        df = raw_store.load_macro_series(sid)
        res = {
            "source": f"macro:{sid}",
            "kind": "macro",
            "rows": 0,
            "latest": None,
            "fresh": False,
            "schema_ok": False,
            "status": "ok",
            "error": "",
        }
        if df.empty:
            res["status"] = "failed"
            res["error"] = "missing_data: no FRED series in warehouse/raw"
        else:
            res["rows"] = int(len(df))
            res["latest"] = str(df["date"].iloc[-1])
            res["schema_ok"] = MACRO_EXPECTED_COLS.issubset(set(df.columns))
            dates = pd.to_datetime(df["date"])
            gaps = dates.diff().dt.days.dropna()
            median_gap = float(gaps.median()) if len(gaps) else 1.0
            threshold = max(3.0, 3.0 * median_gap)
            gap_days = (today - dates.iloc[-1]).days
            if gap_days > threshold:
                res["fresh"] = False
                res["status"] = "stale"
                res["error"] = f"stale_data: latest observation {gap_days:.0f} days old (median gap {median_gap:.1f})"
            else:
                res["fresh"] = True
        out.append(res)
    return out


def check_news(feeds: list[str]) -> list[dict]:
    out = []
    now = time.time()
    for slug in feeds:
        items = raw_store.load_news(slug)
        res = {
            "source": f"news:{slug}",
            "kind": "news",
            "rows": 0,
            "latest": None,
            "fresh": False,
            "schema_ok": True,
            "status": "ok",
            "error": "",
        }
        if not items:
            res["status"] = "failed"
            res["error"] = "missing_data: no news items in warehouse/raw"
        else:
            res["rows"] = len(items)
            latest_ts = max(it.get("ts") or 0 for it in items)
            res["latest"] = datetime.fromtimestamp(latest_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            age_h = (now - latest_ts) / 3600
            if age_h > NEWS_STALE_HOURS:
                res["fresh"] = False
                res["status"] = "stale"
                res["error"] = f"stale_data: newest item {age_h:.1f}h old"
            else:
                res["fresh"] = True
        out.append(res)
    return out


def run_checks() -> list[dict]:
    """All checks for the configured sources."""
    config.load_env()
    watchlist = config.get_list("WATCHLIST")
    series_ids = config.get_list("FRED_SERIES")
    news_urls = config.get_list("NEWS_FEEDS") + config.get_list("NEWS_CRAWL_PAGES")
    news_slugs = [raw_store.slugify(u) for u in news_urls] if hasattr(raw_store, "slugify") else []
    if not news_slugs:
        from collect import news_rss

        news_slugs = [news_rss.slugify(u) for u in news_urls]

    results: list[dict] = []
    results += check_prices(watchlist)
    results += check_macro(series_ids)
    results += check_news(news_slugs)
    return results
