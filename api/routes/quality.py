"""GET /quality — data quality report."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from validate import quality as vquality

router = APIRouter(tags=["quality"])


@router.get("/quality")
def get_quality() -> dict:
    rep = vquality.load_report()
    if rep is None:
        raise HTTPException(status_code=404, detail="no quality report yet (run validate)")
    return rep
