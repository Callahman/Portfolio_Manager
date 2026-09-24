"""Market snapshot (Step 3) — deterministic, in code.

Price moves, volume, sector performance, notable movers, macro indicator
readings. Output: `analyze/analytics/snapshot/{date}.json`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common import config
from collect import raw_store

ANALYTICS_DIR = config.ANALYTICS_DIR

# static sector map (free data has no sector API in v1; unknown -> "other")
SECTORS = {
    "SPY": "broad_market",
    "QQQ": "tech",
    "TLT": "rates",
    "GLD": "commodities",
}


def _pct(series: pd.Series, n: int) -> float | None:
    if len(series) < n + 1:
        return None
    last, prev = float(series.iloc[-1]), float(series.iloc[-1 - n])
    if prev == 0:
        return None
    return round((last / prev - 1) * 100, 3)


def _asset_stats(t: str) -> dict | None:
    df = raw_store.load_price_series(t)
    if df.empty or len(df) < 2:
        return None
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    latest = float(close.iloc[-1])
    return {
        "ticker": t,
        "sector": SECTORS.get(t, "other"),
        "date": str(df["date"].iloc[-1]),
        "close": round(latest, 4),
        "change_1d_pct": _pct(close, 1),
        "change_5d_pct": _pct(close, 5),
        "change_20d_pct": _pct(close, 20),
        "volume_latest": int(vol.iloc[-1]) if pd.notna(vol.iloc[-1]) else None,
        "volume_avg_20d": int(vol.tail(20).mean()) if pd.notna(vol.tail(20).mean()) else None,
        "year_high": round(float(close.tail(252).max()), 4),
        "year_low": round(float(close.tail(252).min()), 4),
    }


def build(watchlist: list[str]) -> dict:
    assets = [a for a in (_asset_stats(t) for t in watchlist) if a]
    gaps = [t for t in watchlist if not any(a["ticker"] == t for a in assets)]

    movers = sorted(assets, key=lambda a: abs(a["change_1d_pct"] or 0), reverse=True)[:5]

    sectors: dict[str, list[float]] = {}
    for a in assets:
        if a["change_5d_pct"] is not None:
            sectors.setdefault(a["sector"], []).append(a["change_5d_pct"])
    sector_perf = {
        s: {"avg_change_5d_pct": round(sum(v) / len(v), 3), "assets": len(v)}
        for s, v in sectors.items()
    }

    # macro indicator readings (latest value + change)
    macro_readings = []
    for sid in config.get_list("FRED_SERIES"):
        df = raw_store.load_macro_series(sid)
        if df.empty:
            continue
        v = df["value"].astype(float)
        macro_readings.append(
            {
                "series": sid,
                "date": str(df["date"].iloc[-1]),
                "value": round(float(v.iloc[-1]), 4),
                "change_1p": round(float(v.iloc[-1] - v.iloc[-2]), 4) if len(v) >= 2 else None,
            }
        )

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assets": assets,
        "notable_movers": [
            {"ticker": m["ticker"], "change_1d_pct": m["change_1d_pct"], "close": m["close"]}
            for m in movers
        ],
        "sector_performance": sector_perf,
        "macro_readings": macro_readings,
        "data_gaps": gaps,
    }


def write(snapshot: dict) -> Path:
    d = ANALYTICS_DIR / "snapshot"
    d.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = d / f"{day}.json"
    p.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return p
