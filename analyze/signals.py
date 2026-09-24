"""Statistical signals (Step 3) — correlations, volatility, trend detection,
signal history with forward-return stats. All math in code (the 4090's roles
interpret, they don't compute — outline §2.3).

Output: `analyze/analytics/signals/{date}.json`.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from common import config
from collect import raw_store

ANALYTICS_DIR = config.ANALYTICS_DIR


def _returns(df: pd.DataFrame) -> pd.Series:
    close = df["close"].astype(float)
    return close.pct_change().dropna()


def _asset_signals(t: str, bench_ret: pd.Series | None) -> dict | None:
    df = raw_store.load_price_series(t)
    if df.empty or len(df) < 25:
        return None
    ret = _returns(df)
    r20 = ret.tail(20)
    vol_20d = float(r20.std())
    ann_vol = round(vol_20d * math.sqrt(252) * 100, 2)

    # trend: OLS slope of normalized log price over 20 days
    px = df["close"].astype(float).tail(20)
    x = np.arange(len(px))
    y = np.log(px.values)
    slope, intercept = np.polyfit(x, y, 1)
    trend_pct_20d = round((math.exp(slope * 20) - 1) * 100, 3)
    yhat = slope * x + intercept
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = round(1 - ss_res / ss_tot, 3) if ss_tot > 0 else None

    corr = None
    if bench_ret is not None:
        j = pd.concat([ret, bench_ret], axis=1).dropna().tail(20)
        if len(j) >= 10:
            corr = round(float(j.iloc[:, 0].corr(j.iloc[:, 1])), 3)

    # 60d max drawdown
    px60 = df["close"].astype(float).tail(60)
    roll_max = px60.cummax()
    dd = (px60 / roll_max - 1).min()
    return {
        "ticker": t,
        "date": str(df["date"].iloc[-1]),
        "volatility_20d_ann_pct": ann_vol,
        "correlation_benchmark_20d": corr,
        "trend_20d_pct": trend_pct_20d,
        "trend_r2": r2,
        "momentum_20d_pct": round(float(px60.iloc[-1] / px60.iloc[0] - 1) * 100, 3) if len(px60) >= 2 else None,
        "max_drawdown_60d_pct": round(float(dd) * 100, 3),
    }


def _correlation_matrix(closes: dict[str, pd.Series]) -> dict:
    df = pd.DataFrame(closes).tail(20).dropna(how="all")
    corr = df.corr()
    return {a: {b: round(float(corr.loc[a, b]), 3) for b in corr.columns} for a in corr.index}


def _signal_history(closes: dict[str, pd.Series]) -> dict:
    """Forward-return stats for recurring rules (backtest-style sanity checks)."""
    out = {}
    for t, s in closes.items():
        if len(s) < 60:
            continue
        ret = s.pct_change().dropna()
        mom = s.pct_change(5).dropna()
        # rule: 5d momentum > 0 -> forward 5d return
        fwd = ret.shift(-5)
        mask = mom > 0
        rows = pd.concat([mom, fwd], axis=1).dropna()
        rows = rows[mask.reindex(rows.index).fillna(False)]
        if len(rows) >= 5:
            out[t] = {
                "rule": "momentum_5d_positive",
                "occurrences": int(len(rows)),
                "avg_forward_5d_pct": round(float(rows.iloc[:, 1].mean()) * 100, 3),
                "positive_rate": round(float((rows.iloc[:, 1] > 0).mean()), 3),
            }
    return out


def build(watchlist: list[str]) -> dict:
    config.load_env()
    benchmark = config.get("BENCHMARK_TIKER", "SPY") or "SPY"
    bench_df = raw_store.load_price_series(benchmark)
    bench_ret = _returns(bench_df) if not bench_df.empty else None

    assets = [a for a in (_asset_signals(t, bench_ret) for t in watchlist) if a]
    closes = {}
    for t in watchlist:
        df = raw_store.load_price_series(t)
        if not df.empty:
            closes[t] = df.set_index(pd.to_datetime(df["date"]))["close"].astype(float)

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark": benchmark,
        "assets": assets,
        "correlation_matrix_20d": _correlation_matrix(closes),
        "signal_history": _signal_history(closes),
    }


def write(signals: dict) -> Path:
    d = ANALYTICS_DIR / "signals"
    d.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = d / f"{day}.json"
    p.write_text(json.dumps(signals, indent=2), encoding="utf-8")
    return p
