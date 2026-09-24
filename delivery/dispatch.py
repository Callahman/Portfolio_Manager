"""Delivery dispatch (Step 7) — what happens after a recommendation lands.

after_recommendation(rec, result):
  1. write the markdown report (reports/)
  2. email the summary (SMTP, best-effort)
  3. email open failures if any (SMTP, best-effort)

Best-effort by contract: delivery must never block or roll back the
portfolio apply.
"""
from __future__ import annotations

import logging
from pathlib import Path

from common import failures as cf
from delivery import email, report

log = logging.getLogger(__name__)


def after_recommendation(rec: dict, result: dict) -> dict:
    out: dict = {}
    try:
        p = report.write_report(rec, result)
        out["report"] = str(p)
    except Exception as e:  # noqa: BLE001
        log.error("report FAILED: %s", e)
        out["report_error"] = str(e)

    try:
        rp = Path(out["report"]) if out.get("report") else None
        md = rp.read_text(encoding="utf-8") if rp and rp.exists() else ""
        out["email"] = email.send_run_summary(md)
    except Exception as e:  # noqa: BLE001
        log.error("email FAILED: %s", e)
        out["email_error"] = str(e)

    try:
        open_f = [
            {
                "failure_id": r.failure_id,
                "source": r.source,
                "message": r.message,
            }
            for r in cf.open_reports()
        ]
        if open_f:
            out["failure_email"] = email.send_failure_summary(open_f)
    except Exception as e:  # noqa: BLE001
        log.error("failure email FAILED: %s", e)
        out["failure_email_error"] = str(e)
    return out


def after_run_failure(reason: str) -> None:
    """SMTP summary on pipeline run failures (called by the pipeline runner)."""
    try:
        email.send("Portfolio Manager — run failure", reason[:20000])
    except Exception as e:  # noqa: BLE001
        log.error("failure email FAILED: %s", e)
