"""Risk metrics (Step 3) — portfolio risk, position/sector exposure, tail
stats, proposed-limit checks.

Reads the paper portfolio (portfolio/portfolio.db) if present; otherwise
computes universe-level stats and says so. Limit checks run against the
risk policy (defaults: max position 40%, max sector 60%, max 10 trades/day —
configurable, later hardened by the deterministic risk engine, outline §5.9).

Output: `analyze/analytics/risk/{date}.json`.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common import config
from collect import raw_store
from analyze import snapshot as snap

ANALYTICS_DIR = config.ANALYTICS_DIR

POLICY = {
    "max_position_pct": 40.0,
    "max_sector_pct": 60.0,
    "max_trades_per_day": 10,
}


def _asset_tail(t: str) -> dict | None:
    df = raw_store.load_price_series(t)
    if df.empty or len(df) < 30:
        return None
    ret = df["close"].astype(float).pct_change().dropna()
    r = ret.tail(252)
    return {
        "ticker": t,
        "daily_vol_pct": round(float(r.std()) * 100, 3),
        "var_95_daily_pct": round(float(-r.quantile(0.05)) * 100, 3),  # historical VaR
        "worst_day_pct": round(float(r.min()) * 100, 3),
        "skew": round(float(r.skew()), 3),
    }


def _read_portfolio() -> dict | None:
    db = config.PORTFOLIO_DIR / "portfolio.db"
    if not db.exists():
        return None
    conn = sqlite3.connect(db)
    try:
        try:
            pos = pd.read_sql_query(
                "SELECT ticker, shares, avg_cost FROM positions WHERE shares > 0", conn
            )
            cash = pd.read_sql_query("SELECT value FROM cash LIMIT 1", conn)
            cash_val = float(cash["value"].iloc[0]) if not cash.empty else 0.0
        except pd.EmptyDataError:
            return None
        if pos.empty:
            return {"positions": [], "cash": cash_val, "total": cash_val, "weights": {}}
        # latest close per ticker
        total = cash_val
        rows = []
        for _, p in pos.iterrows():
            df = raw_store.load_price_series(p["ticker"])
            close = float(df["close"].iloc[-1]) if not df.empty else float(p["avg_cost"])
            mv = float(p["shares"]) * close
            total += mv
            rows.append({"ticker": p["ticker"], "shares": float(p["shares"]), "close": close, "market_value": round(mv, 2)})
        weights = {r["ticker"]: round(r["market_value"] / total * 100, 2) if total else 0 for r in rows}
        sector_exp: dict[str, float] = {}
        for r in rows:
            s = snap.SECTORS.get(r["ticker"], "other")
            sector_exp[s] = round(sector_exp.get(s, 0) + weights[r["ticker"]], 2)
        return {
            "positions": rows,
            "cash": round(cash_val, 2),
            "total": round(total, 2),
            "weights": weights,
            "sector_exposure": sector_exp,
            "concentration_hhi": round(sum(w * w for w in weights.values()), 1),
        }
    finally:
        conn.close()


def _limit_checks(pf: dict | None) -> list[dict]:
    checks = []
    if pf is None or not pf.get("weights"):
        return checks
    for t, w in pf["weights"].items():
        if w > POLICY["max_position_pct"]:
            checks.append({"limit": "max_position_pct", "ticker": t, "value": w, "policy": POLICY["max_position_pct"], "violated": True})
    for s, w in (pf.get("sector_exposure") or {}).items():
        if w > POLICY["max_sector_pct"]:
            checks.append({"limit": "max_sector_pct", "sector": s, "value": w, "policy": POLICY["max_sector_pct"], "violated": True})
    return checks


def build(watchlist: list[str]) -> dict:
    portfolio = _read_portfolio()
    tail = [x for x in (_asset_tail(t) for t in watchlist) if x]
    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy": POLICY,
        "portfolio": portfolio,
        "asset_tail_stats": tail,
        "limit_checks": _limit_checks(portfolio),
        "note": None if portfolio else "no paper portfolio yet — universe-level stats only",
    }


def write(risk: dict) -> Path:
    d = ANALYTICS_DIR / "risk"
    d.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = d / f"{day}.json"
    p.write_text(json.dumps(risk, indent=2), encoding="utf-8")
    return p
