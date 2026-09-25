"""Paper execution (Step 6) — apply a team recommendation at close prices
with an assumed transaction cost (churn must be visible in the P&L).

Recommendation shape (from POST /recommendation):
  {
    "actions": [{"ticker": "SPY", "side": "buy"|"sell", "shares": 1.5,
                 "rationale": "..."}],
    "rationale": "overall recommendation rationale"
  }

Fractional shares are allowed. Sells are capped at the current position.
"""
from __future__ import annotations

import json
import sqlite3
import time

from portfolio import db


def _tx_cost(value: float, cost_bps: float) -> float:
    return abs(value) * (cost_bps / 10000.0)


def apply_recommendation(
    rec: dict,
    prices: dict[str, float],
    cost_bps: float = 5.0,
    db_path: sqlite3.Connection | None = None,
) -> dict:
    """Apply a recommendation. `prices`: ticker -> latest close."""
    conn = db.connect(db_path) if db_path is None else db_path
    executed: list[dict] = []
    errors: list[str] = []

    cash_row = conn.execute("SELECT value FROM cash WHERE id = 1").fetchone()
    cash = float(cash_row[0]) if cash_row else 0.0

    for act in rec.get("actions", []):
        ticker = act.get("ticker")
        side = (act.get("side") or "").lower()
        shares = float(act.get("shares") or 0)
        if not ticker or shares <= 0 or side not in ("buy", "sell"):
            errors.append(f"invalid action: {act}")
            continue
        if ticker not in prices:
            errors.append(f"no price for {ticker}")
            continue
        price = float(prices[ticker])
        value = shares * price
        tx = _tx_cost(value, cost_bps)

        pos = conn.execute("SELECT shares, avg_cost FROM positions WHERE ticker=?", (ticker,)).fetchone()
        held = float(pos[0]) if pos else 0.0
        avg_cost = float(pos[1]) if pos else 0.0

        if side == "buy":
            if value + tx > cash + 1e-9:
                # shrink to affordable (fractional shares)
                shares = max(0.0, (cash / (price * (1 + cost_bps / 10000.0))))
                value = shares * price
                tx = _tx_cost(value, cost_bps)
                if shares <= 0:
                    errors.append(f"insufficient cash for buy {ticker}")
                    continue
            new_shares = held + shares
            new_avg = (held * avg_cost + value) / new_shares if new_shares else 0.0
            cash -= value + tx
            conn.execute(
                "INSERT OR REPLACE INTO positions (ticker, shares, avg_cost) VALUES (?,?,?)",
                (ticker, new_shares, new_avg),
            )
        else:  # sell
            shares = min(shares, held)
            if shares <= 0:
                errors.append(f"no position to sell for {ticker}")
                continue
            value = shares * price
            tx = _tx_cost(value, cost_bps)
            cash += value - tx
            new_shares = held - shares
            if new_shares <= 1e-9:
                conn.execute("DELETE FROM positions WHERE ticker=?", (ticker,))
            else:
                conn.execute(
                    "UPDATE positions SET shares=? WHERE ticker=?", (new_shares, ticker)
                )
            value = shares * price  # recompute after cap

        conn.execute(
            "INSERT INTO trades (ts, ticker, side, shares, price, cost_bps, tx_cost, rationale) VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), ticker, side, shares, price, cost_bps, tx, act.get("rationale", "")),
        )
        executed.append(
            {"ticker": ticker, "side": side, "shares": round(shares, 6), "price": price, "tx_cost": round(tx, 4)}
        )

    conn.execute("UPDATE cash SET value=? WHERE id=1", (cash,))
    conn.execute(
        "INSERT INTO decisions (ts, recommendation_json) VALUES (?,?)",
        (time.time(), json.dumps(rec, ensure_ascii=False)),
    )
    conn.commit()
    return {"executed": executed, "errors": errors, "cash_after": round(cash, 2)}


def mark_to_market(
    prices: dict[str, float],
    date: str,
    benchmark_close: float | None = None,
    start_balance: float | None = None,
    db_path: sqlite3.Connection | None = None,
) -> dict:
    """Write a daily mark row. benchmark_total is scaled from the prior mark
    (first mark = start_balance)."""
    conn = db.connect(db_path) if db_path is None else db_path
    # Auto-seed the starting balance on first use (idempotent), so the first
    # daily mark bootstraps the paper portfolio instead of crashing on an
    # empty cash table.
    if conn.execute("SELECT 1 FROM cash WHERE id=1").fetchone() is None:
        conn.execute("INSERT INTO cash (id, value) VALUES (1, ?)", (float(start_balance or 0.0),))
        conn.commit()
    cash = float(conn.execute("SELECT value FROM cash WHERE id=1").fetchone()[0])
    pos_value = 0.0
    for ticker, shares, _ in conn.execute("SELECT ticker, shares, avg_cost FROM positions").fetchall():
        close = prices.get(ticker)
        if close is not None:
            pos_value += float(shares) * float(close)
    total = cash + pos_value

    prev = conn.execute("SELECT benchmark_close, benchmark_total FROM marks ORDER BY date DESC LIMIT 1").fetchone()
    bench_total = None
    if benchmark_close is not None:
        if prev is None or prev[1] is None:
            bench_total = float(start_balance or 0.0)
        else:
            bench_total = float(prev[1]) * (float(benchmark_close) / float(prev[0]))

    conn.execute(
        """INSERT OR REPLACE INTO marks (date, total, cash, positions_value, benchmark_close, benchmark_total)
           VALUES (?,?,?,?,?,?)""",
        (date, total, cash, pos_value, benchmark_close, bench_total),
    )
    conn.commit()
    return {
        "date": date,
        "total": round(total, 2),
        "cash": round(cash, 2),
        "positions_value": round(pos_value, 2),
        "benchmark_total": round(bench_total, 2) if bench_total is not None else None,
    }
