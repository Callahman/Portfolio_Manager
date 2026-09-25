"""GET /metrics — read-only paper-portfolio evaluation metrics (Step 4).

Read-only: returns the portfolio P&L, drawdown, Sharpe, trade count/turnover,
and SPY-benchmark comparison. Lets the 4090 capture a P&L baseline when it
records a decision (Epic 7.5 decision journal).
"""
from __future__ import annotations

from fastapi import APIRouter

from portfolio import metrics as pmetrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def get_metrics() -> dict:
    return pmetrics.compute_metrics()
