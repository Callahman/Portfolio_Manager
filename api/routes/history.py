"""GET /history — conversation history (rolling window).

Sessions live in history/sessions/{session_id}.jsonl (one JSON object per
line: role, pod, round, content, ts). This endpoint returns the most
recent sessions (bounded) — the full record stays on disk / in archives.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Query

from common import config

router = APIRouter(tags=["history"])

HISTORY_DIR = config.HISTORY_DIR
SESSIONS_DIR = HISTORY_DIR / "sessions"


@router.get("/history")
def get_history(limit: int = Query(5, le=50)) -> dict:
    if not SESSIONS_DIR.is_dir():
        return {"count": 0, "sessions": []}
    files = sorted(SESSIONS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    sessions = []
    for f in files:
        entries = []
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        sessions.append(
            {
                "session_id": f.stem,
                "entries": len(entries),
                "latest": entries[-1] if entries else None,
            }
        )
    return {"count": len(sessions), "sessions": sessions}


@router.get("/history/{session_id}")
def get_session(session_id: str) -> dict:
    f = SESSIONS_DIR / f"{session_id}.jsonl"
    if not f.exists():
        return {"error": "not found"}
    entries = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"session_id": session_id, "entries": entries}
