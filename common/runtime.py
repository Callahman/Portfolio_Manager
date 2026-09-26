"""Runtime state shared across the 1080 services (Epic 11.3).

The 4090's team-runtime health URL is registered here (ad-hoc, live IP) by
POST /register; the dashboard's monitoring view reads it, falling back to the
static TEAM_RUNTIME_HEALTH_URL if no registration is present.
"""
from __future__ import annotations

import json
from pathlib import Path

from common import config

REGISTRATION_FILE: Path = config.REPO_ROOT / "runtime" / "team_runtime.json"


def load_registration() -> dict | None:
    """Read the stored 4090 health registration (None if absent/invalid)."""
    if not REGISTRATION_FILE.exists():
        return None
    try:
        return json.loads(REGISTRATION_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_registration(record: dict) -> None:
    """Persist a 4090 health registration (creates runtime/ if needed)."""
    REGISTRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRATION_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
