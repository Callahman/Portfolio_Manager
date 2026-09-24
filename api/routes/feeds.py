"""GET /feeds/{role} — per-role bounded feeds (built on the 1080 by
analyze/feeds.py; served here)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from analyze import feeds as afeeds

router = APIRouter(tags=["feeds"])


@router.get("/feeds/{role}")
def get_feed(role: str) -> dict:
    try:
        return afeeds.build_feed(role)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/feeds")
def list_roles() -> dict:
    return {"roles": afeeds.all_roles()}
