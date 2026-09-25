"""Conversation history (Epic 7, Story 7.5) — per-session JSONL + markdown,
rolling window, decision journal.

Layout (HISTORY_DIR):
  sessions/{session_id}.jsonl   one JSON object per entry (role, pod, round,
                                content, ts)
  sessions/{session_id}.md      markdown mirror of the transcript
  decision_journal.jsonl        one JSON object per posted recommendation
                                (ts, session_id, recommendation, result)
  decision_journal.md           markdown mirror

Rolling window: the HISTORY_WINDOW_SESSIONS (30) most recent sessions,
pruned to HISTORY_CAP_MB (500). Prune runs on session start/end and in
workflows/maintenance.py.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from common import config

log = logging.getLogger(__name__)

HISTORY_DIR = config.HISTORY_DIR
SESSIONS_DIR = HISTORY_DIR / "sessions"
JOURNAL_PATH = HISTORY_DIR / "decision_journal.jsonl"
JOURNAL_MD = HISTORY_DIR / "decision_journal.md"


def _ensure_sessions_dir() -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR


def _session_path(session_id: str) -> Path:
    return _ensure_sessions_dir() / f"{session_id}.jsonl"


def start_session(session_id: str, meta: dict | None = None) -> Path:
    p = _session_path(session_id)
    entry = {"type": "session_meta", "session_id": session_id, "started": time.time(), "meta": meta or {}}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return p


def append_entry(session_id: str, entry: dict) -> None:
    p = _session_path(session_id)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_session(session_id: str) -> list[dict]:
    p = _session_path(session_id)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def list_sessions(limit: int | None = None) -> list[str]:
    if not SESSIONS_DIR.is_dir():
        return []
    files = sorted(SESSIONS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    ids = [f.stem for f in files]
    return ids[:limit] if limit else ids


def _content_md(content) -> str:
    if isinstance(content, dict):
        lines = []
        if content.get("summary"):
            lines.append(f"- {content['summary']}")
        for fnd in content.get("findings", []) or []:
            lines.append(f"  - {fnd.get('point')} ({fnd.get('evidence')})")
        if content.get("recommendation"):
            lines.append(f"- recommendation: {content['recommendation']}")
        if content.get("final_recommendation"):
            fr = content["final_recommendation"]
            lines.append(f"- final: {fr.get('rationale')}")
            for a in fr.get("actions", []):
                lines.append(f"  - {a.get('side')} {a.get('shares')} {a.get('ticker')} — {a.get('rationale')}")
        if content.get("allocation_actions"):
            for a in content["allocation_actions"]:
                lines.append(f"  - {a.get('side')} {a.get('shares')} {a.get('ticker')} — {a.get('rationale')}")
        return "\n".join(lines) if lines else "```json\n" + json.dumps(content, indent=2) + "\n```"
    if isinstance(content, str):
        return content
    return "```json\n" + json.dumps(content, indent=2) + "\n```"


def write_markdown(session_id: str) -> Path | None:
    entries = load_session(session_id)
    if not entries:
        return None
    md: list[str] = [f"# Session {session_id}", ""]
    for e in entries:
        if e.get("type") == "session_meta":
            started = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(e.get("started", 0)))
            md.append(f"- started: {started}")
            md.append(f"- meta: {json.dumps(e.get('meta', {}))}")
            md.append("")
            continue
        pod = e.get("pod", "-")
        role = e.get("role", "?")
        rnd = e.get("round")
        md.append(f"## {pod} — {role}" + (f" (round {rnd})" if rnd else ""))
        md.append("")
        md.append(_content_md(e.get("content")))
        md.append("")
    p = SESSIONS_DIR / f"{session_id}.md"
    p.write_text("\n".join(md), encoding="utf-8")
    return p


def record_decision(session_id: str, recommendation: dict, result: dict | None) -> None:
    entry = {"ts": time.time(), "session_id": session_id, "recommendation": recommendation, "result": result}
    with JOURNAL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _write_journal_md()


def decision_journal() -> list[dict]:
    if not JOURNAL_PATH.exists():
        return []
    out = []
    for line in JOURNAL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _write_journal_md() -> None:
    entries = decision_journal()
    md = ["# Decision journal", ""]
    for e in entries:
        ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(e.get("ts", 0)))
        rec = e.get("recommendation", {})
        md.append(f"## {ts} — session {e.get('session_id')}")
        md.append(f"- rationale: {rec.get('rationale', '(none)')}")
        for a in rec.get("actions", []):
            md.append(f"  - {a.get('side')} {a.get('shares')} {a.get('ticker')} — {a.get('rationale', '')}")
        result = e.get("result") or {}
        if result.get("error"):
            md.append(f"- result: ERROR {result['error']}")
        else:
            md.append(f"- result: HTTP {result.get('status_code')} — {json.dumps(result.get('body', {}))[:300]}")
        md.append("")
    JOURNAL_MD.write_text("\n".join(md), encoding="utf-8")


def prune(window: int | None = None, cap_mb: float | None = None) -> int:
    """Rolling window: keep the `window` most recent sessions, then delete the
    oldest until the sessions dir is under `cap_mb`. Returns files deleted."""
    _ensure_sessions_dir()
    window = window or config.get_int("HISTORY_WINDOW_SESSIONS", 30)
    cap_mb = cap_mb or config.get_float("HISTORY_CAP_MB", 500.0)
    files = sorted(SESSIONS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    deleted = 0
    for f in files[window:]:
        for victim in (f, SESSIONS_DIR / (f.stem + ".md")):
            if victim.exists():
                victim.unlink()
                deleted += 1
    kept = files[:window]

    def total_mb() -> float:
        tot = 0
        for f in SESSIONS_DIR.iterdir():
            if f.is_file():
                tot += f.stat().st_size
        return tot / (1024 * 1024)

    i = len(kept) - 1
    while total_mb() > cap_mb and i >= 0:
        f = kept[i]
        for victim in (f, SESSIONS_DIR / (f.stem + ".md")):
            if victim.exists():
                victim.unlink()
                deleted += 1
        i -= 1
    if deleted:
        log.info("history prune: deleted %d files", deleted)
    return deleted
