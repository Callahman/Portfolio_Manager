"""Fundamentals (Step 3) — sector rotation, ticker-specific news/events,
valuation proxies.

v1 note: earnings/valuation detail needs extra sources (outline §5.3 —
earnings calendar, etc.); until those land, this module derives what the
free data supports (relative strength, price-range percentile, news events)
and lists the rest as data_gaps. The schema is stable so future sources
slot in without restructuring.

Output: `analyze/analytics/fundamentals/{date}.json`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from common import config
from collect import raw_store
from analyze import snapshot as snap

ANALYTICS_DIR = config.ANALYTICS_DIR


def _ticker_events(ticker: str, items: list[dict], limit: int = 10) -> list[dict]:
    pat = re.compile(rf"\b{re.escape(ticker)}\b", re.IGNORECASE)
    hits = [it for it in items if pat.search(it.get("title", ""))]
    return [
        {"title": it.get("title", ""), "link": it.get("link", ""), "ts": it.get("ts")}
        for it in hits[:limit]
    ]


def build(watchlist: list[str]) -> dict:
    config.load_env()
    news_items: list[dict] = []
    for slug in raw_store.all_news_feeds():
        news_items.extend(raw_store.load_news(slug))
    news_items.sort(key=lambda x: x.get("ts") or 0, reverse=True)

    tickers = []
    for t in watchlist:
        df = raw_store.load_price_series(t)
        if df.empty:
            continue
        close = df["close"].astype(float)
        yr = close.tail(252)
        pos = float(close.iloc[-1])
        lo, hi = float(yr.min()), float(yr.max())
        pctile = round((pos - lo) / (hi - lo) * 100, 1) if hi > lo else None
        n = len(close)
        rs = {}
        for label, k in (("5d", 5), ("20d", 20)):
            if n > k:
                rs[f"relative_strength_{label}"] = round(float(close.iloc[-1] / close.iloc[-1 - k] - 1) * 100, 3)
        tickers.append(
            {
                "ticker": t,
                "sector": snap.SECTORS.get(t, "other"),
                "price_range_percentile_1y": pctile,
                "relative_strength": rs,
                "events": _ticker_events(t, news_items),
            }
        )

    # sector rotation: rank sectors by 5d relative strength
    by_sector: dict[str, list[float]] = {}
    for t in tickers:
        rs5 = t["relative_strength"].get("relative_strength_5d")
        if rs5 is not None:
            by_sector.setdefault(t["sector"], []).append(rs5)
    rotation = sorted(
        (
            {"sector": s, "avg_rs_5d_pct": round(sum(v) / len(v), 3), "assets": len(v)}
            for s, v in by_sector.items()
        ),
        key=lambda x: x["avg_rs_5d_pct"],
        reverse=True,
    )

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tickers": tickers,
        "sector_rotation": rotation,
        "data_gaps": [
            "earnings calendar (outline §5.3)",
            "valuation detail — P/E, FCF (outline §5.3)",
        ],
    }


def write(fund: dict) -> Path:
    d = ANALYTICS_DIR / "fundamentals"
    d.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = d / f"{day}.json"
    p.write_text(json.dumps(fund, indent=2), encoding="utf-8")
    return p
