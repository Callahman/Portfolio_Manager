"""POST /register — the 4090 announces its team-runtime health URL (Epic 11.3).

The 4090 is strictly ad-hoc (no schedule, no static IP), so on startup it
determines its own LAN IP and posts it here. The 1080 stores the health URL in
runtime/team_runtime.json; the dashboard's monitoring view reads it (falling
back to TEAM_RUNTIME_HEALTH_URL if the file is absent). This is the second
write endpoint, alongside POST /recommendation.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from common import runtime as cruntime

log = logging.getLogger(__name__)

router = APIRouter(tags=["register"])


def _validate_health_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=422, detail="health_url must be a non-empty string")
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="health_url must be an http(s) URL")
    return url


@router.post("/register")
def register_team_runtime(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="register must be an object")
    health_url = _validate_health_url(payload.get("health_url", ""))
    ip = payload.get("ip", "")
    record = {
        "ip": ip,
        "health_url": health_url,
        "registered_at": time.time(),
    }
    cruntime.write_registration(record)
    log.info("registered team runtime %s (ip=%s)", health_url, ip)
    return {"registered": True, "health_url": health_url}
