"""Dashboard FastAPI app (Step 7).

Bind: DASHBOARD_HOST/DASHBOARD_PORT (default 0.0.0.0:8300, LAN).

Usage:
  python -m delivery.dashboard.app
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from common import config
from collect import raw_store
from validate import quality as vquality
from common import failures as cf
from portfolio import metrics as pmetrics

log = logging.getLogger(__name__)

TEMPLATE = Path(__file__).parent / "templates" / "index.html"


def create_app() -> FastAPI:
    app = FastAPI(title="Portfolio Manager dashboard")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return TEMPLATE.read_text(encoding="utf-8")

    @app.get("/api/status")
    def status() -> dict:
        q = vquality.load_report()
        fetches = raw_store.recent_fetches(hours=48)
        return {
            "quality_report_at": (q or {}).get("generated_at"),
            "coverage": (q or {}).get("coverage"),
            "recent_fetches": fetches[:20],
            "next_runs": "see systemd timers (pm-collect-*.timer)",
        }

    @app.get("/api/freshness")
    def freshness() -> dict:
        q = vquality.load_report()
        if not q:
            return {"sources": {}}
        return {
            "sources": {
                src: {
                    "status": r.get("status"),
                    "latest": r.get("latest"),
                    "rows": r.get("rows"),
                    "error": r.get("error"),
                }
                for src, r in q.get("sources", {}).items()
            }
        }

    @app.get("/api/history")
    def history() -> dict:
        sessions_dir = config.HISTORY_DIR / "sessions"
        if not sessions_dir.is_dir():
            return {"count": 0, "sessions": []}
        files = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        out = []
        for f in files:
            entries = []
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            out.append(
                {
                    "session_id": f.stem,
                    "entries": len(entries),
                    "transcript": entries,
                }
            )
        return {"count": len(out), "sessions": out}

    @app.get("/api/recommendations")
    def recommendations() -> dict:
        db = config.PORTFOLIO_DIR / "portfolio.db"
        if not db.exists():
            return {"count": 0, "recommendations": []}
        conn = sqlite3.connect(db)
        try:
            rows = conn.execute(
                "SELECT ts, recommendation_json, outcome_note FROM decisions ORDER BY ts DESC LIMIT 20"
            ).fetchall()
        finally:
            conn.close()
        return {
            "count": len(rows),
            "recommendations": [
                {"ts": r[0], "recommendation": json.loads(r[1]), "outcome_note": r[2]} for r in rows
            ],
        }

    @app.get("/api/portfolio")
    def portfolio() -> dict:
        m = pmetrics.compute_metrics()
        db = config.PORTFOLIO_DIR / "portfolio.db"
        positions, trades = [], []
        if db.exists():
            conn = sqlite3.connect(db)
            try:
                positions = [
                    {"ticker": r[0], "shares": r[1], "avg_cost": r[2]}
                    for r in conn.execute("SELECT ticker, shares, avg_cost FROM positions ORDER BY ticker")
                ]
                trades = [
                    {"ts": r[0], "ticker": r[1], "side": r[2], "shares": r[3], "price": r[4], "tx_cost": r[5]}
                    for r in conn.execute(
                        "SELECT ts, ticker, side, shares, price, tx_cost FROM trades ORDER BY ts DESC LIMIT 50"
                    )
                ]
            finally:
                conn.close()
        return {"metrics": m, "positions": positions, "trades": trades}

    @app.get("/api/failures")
    def failures() -> dict:
        reps = cf.load_reports()
        return {
            "count": len(reps),
            "failures": [
                {
                    "failure_id": r.failure_id,
                    "status": r.status,
                    "error_class": r.error_class,
                    "source": r.source,
                    "message": r.message,
                    "occurrence_count": r.occurrence_count,
                }
                for r in reps
            ],
        }

    @app.get("/api/monitoring")
    def monitoring() -> dict:
        """Health view (Epic 11.3): API self-status, 4090 reachability,
        pipeline state, quality-report age."""
        q = vquality.load_report()
        fourzero: dict = {}
        url = (config.get("TEAM_RUNTIME_HEALTH_URL") or "").strip()
        if url:
            try:
                r = requests.get(url, timeout=5)
                fourzero = {
                    "reachable": True,
                    "url": url,
                    "status": r.json() if r.ok else f"HTTP {r.status_code}",
                }
            except Exception as e:
                fourzero = {"reachable": False, "url": url, "error": str(e)}
        else:
            fourzero = {"reachable": None, "note": "TEAM_RUNTIME_HEALTH_URL not set"}
        return {
            "api": {"status": "ok"},
            "quality_report_at": (q or {}).get("generated_at"),
            "team_runtime_4090": fourzero,
            "pipeline": _pipeline_state(),
        }

    @app.get("/api/decisions")
    def decisions() -> dict:
        """Decision journal (Epic 7.5): posted recommendations + results."""
        from common import history as chist

        entries = chist.decision_journal()
        return {"count": len(entries), "decisions": entries[-50:][::-1]}

    return app


def _pipeline_state() -> dict:
    p = config.HISTORY_DIR / "pipeline" / "state.json"
    if not p.exists():
        return {"available": False}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"available": False}


def main() -> int:
    config.load_env()
    import uvicorn

    host = config.get("DASHBOARD_HOST", "0.0.0.0") or "0.0.0.0"
    port = config.get_int("DASHBOARD_PORT", 8300)
    log.info("starting dashboard on %s:%d", host, port)
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main())
