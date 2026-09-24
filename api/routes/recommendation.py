"""POST /recommendation — the ONLY write endpoint (Step 4).

Accepts a team recommendation, applies it to the paper portfolio at the
latest close prices (with assumed transaction cost), and triggers
delivery (report + email). The recommendation and its rationale are
recorded with the decision.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from common import config
from collect import raw_store
from portfolio import db, execute

router = APIRouter(tags=["recommendation"])


@router.post("/recommendation")
def post_recommendation(rec: dict) -> dict:
    if not isinstance(rec, dict) or "actions" not in rec:
        raise HTTPException(status_code=422, detail="recommendation must be an object with 'actions'")

    config.load_env()
    cost_bps = config.get_float("TX_COST_BPS", 5.0)

    # latest close per ticker from warehouse/raw
    prices: dict[str, float] = {}
    for t in raw_store.all_price_tickers():
        df = raw_store.load_price_series(t)
        if not df.empty:
            prices[t] = float(df["close"].iloc[-1])
    if not prices:
        raise HTTPException(status_code=503, detail="no price data in warehouse/raw yet")

    result = execute.apply_recommendation(rec, prices, cost_bps)
    if not result["executed"] and result["errors"]:
        raise HTTPException(status_code=422, detail={"errors": result["errors"]})

    # trigger delivery (report + email) — best-effort; never blocks the apply
    delivery_error = None
    try:
        from delivery import dispatch

        dispatch.after_recommendation(rec, result)
    except Exception as e:  # noqa: BLE001
        delivery_error = str(e)

    return {
        "applied": True,
        "executed": result["executed"],
        "errors": result["errors"],
        "cash_after": result["cash_after"],
        "delivery": "triggered" if delivery_error is None else f"failed: {delivery_error}",
    }
