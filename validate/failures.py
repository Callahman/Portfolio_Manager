"""Structured failure reports (Step 2) — emission logic.

For every source whose check did not pass, emit/update a structured
failure report (common schema: error class, stage, source, message, log
excerpt, first/last occurrence). These are the input to the role-scoped
self-modification loop (outline §2.9). A source that recovers on a later
run has its open report closed (status=fixed).
"""
from __future__ import annotations

from common import failures as cf
from common import config

VALIDATED_DIR = config.VALIDATED_DIR
FAILURE_DIR = VALIDATED_DIR / "failures"

ERROR_CLASS_BY_STATUS = {
    "stale": "stale_data",
    "failed": "fetch_failed",
}


def emit_failure_reports(results: list[dict]) -> list[str]:
    """Create/update reports for bad sources, close reports for recovered ones.

    Returns the list of open failure ids after this run.
    """
    bad = {r["source"] for r in results if r["status"] != "ok"}
    good = {r["source"] for r in results if r["status"] == "ok"}

    for r in results:
        if r["status"] == "ok":
            continue
        error_class = "schema_mismatch" if "schema_mismatch" in r.get("error", "") else ERROR_CLASS_BY_STATUS.get(r["status"], "fetch_failed")
        existing = cf.find_by_source(r["source"], FAILURE_DIR)
        if existing is not None:
            existing.last_occurrence = __import__("time").time()
            existing.occurrence_count += 1
            existing.message = r.get("error") or existing.message
            cf.save_report(existing, FAILURE_DIR)
        else:
            rep = cf.FailureReport(
                failure_id=cf.new_failure_id(),
                error_class=error_class,
                stage="collect",
                source=r["source"],
                message=r.get("error") or f"check status={r['status']}",
                log_excerpt=json_excerpt(r),
            )
            cf.save_report(rep, FAILURE_DIR)

    # close reports for sources that recovered this run
    for rep in cf.load_reports(FAILURE_DIR):
        if rep.status == "open" and rep.source in good:
            rep.status = "fixed"
            cf.save_report(rep, FAILURE_DIR)

    return [r.failure_id for r in cf.open_reports(FAILURE_DIR)]


def json_excerpt(r: dict) -> str:
    import json

    return json.dumps(
        {k: r.get(k) for k in ("source", "kind", "rows", "latest", "status", "error")},
        indent=2,
    )


if __name__ == "__main__":
    from validate.checks import run_checks

    config.load_env()
    results = run_checks()
    open_ids = emit_failure_reports(results)
    print("open failures:", open_ids)
