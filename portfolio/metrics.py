"""Evaluation metrics (Step 6) — P&L, drawdown, Sharpe, trade count/turnover,
vs the SPY benchmark. All math in code.

Also the entry point for the daily mark-to-market job (systemd timer):
  python -m portfolio.metrics mark
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

from common import config
from collect import raw_store
from portfolio import db, execute

log = logging.getLogger(__name__)


def compute_metrics(conn: sqlite3.Connection | None = None) -> dict:
    own = conn is None
    conn = conn or db.connect()
    try:
        marks = pd.read_sql_query(
            "SELECT date, total, cash, positions_value, benchmark_close, benchmark_total FROM marks ORDER BY date",
            conn,
        )
        if marks.empty:
            return {"available": False, "reason": "no marks yet"}

        total = marks["total"].astype(float)
        first, last = float(total.iloc[0]), float(total.iloc[-1])
        cum_return = round((last / first - 1) * 100, 3) if first else None

        roll_max = total.cummax()
        max_dd = round(float((total / roll_max - 1).min()) * 100, 3)

        # Sharpe (annualized, rf=0) from daily total returns
        rets = total.pct_change().dropna()
        sharpe = None
        if len(rets) >= 2 and float(rets.std()) > 0:
            sharpe = round(float(rets.mean() / rets.std()) * (252 ** 0.5), 3)

        bench = marks["benchmark_total"].dropna()
        bench_return = None
        bench_dd = None
        if len(bench) >= 2:
            b = bench.astype(float)
            bench_return = round((float(b.iloc[-1]) / float(b.iloc[0]) - 1) * 100, 3)
            bb = b.cummax()
            bench_dd = round(float((b / bb - 1).min()) * 100, 3)

        trades = pd.read_sql_query(
            "SELECT ticker, side, shares, price, tx_cost FROM trades", conn
        )
        n_trades = int(len(trades))
        turnover = None
        if n_trades and last:
            trade_value = float((trades["shares"] * trades["price"]).sum())
            turnover = round(trade_value / last, 3)

        return {
            "available": True,
            "as_of": str(marks["date"].iloc[-1]),
            "total": round(last, 2),
            "cumulative_return_pct": cum_return,
            "max_drawdown_pct": max_dd,
            "sharpe_ann": sharpe,
            "n_trades": n_trades,
            "turnover": turnover,
            "benchmark": {
                "cumulative_return_pct": bench_return,
                "max_drawdown_pct": bench_dd,
                "excess_return_pct": (
                    round(cum_return - bench_return, 3)
                    if cum_return is not None and bench_return is not None
                    else None
                ),
            },
        }
    finally:
        if own:
            conn.close()


def mark_daily() -> int:
    """Daily mark-to-market job: latest closes from warehouse/raw."""
    config.load_env()
    benchmark = config.get("BENCHMARK_TIKER", "SPY") or "SPY"
    prices: dict[str, float] = {}
    for t in raw_store.all_price_tickers():
        df = raw_store.load_price_series(t)
        if not df.empty:
            prices[t] = float(df["close"].iloc[-1])
    if not prices:
        log.error("no price series in warehouse/raw — cannot mark")
        return 1

    start_balance = config.get_float("PORTFOLIO_START_BALANCE", 10000.0)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = execute.mark_to_market(prices, date, prices.get(benchmark), start_balance)
    log.info("mark: %s", row)
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "mark":
        return mark_daily()
    m = compute_metrics()
    import json

    print(json.dumps(m, indent=2))
    return 0 if m.get("available") else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main(sys.argv[1:]))
