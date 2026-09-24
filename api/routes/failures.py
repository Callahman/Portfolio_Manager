"""GET /failures — structured failure reports (open by default)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from common import failures as cf
from common import config

router = APIRouter(tags=["failures"])


@router.get("/failures")
def get_failures(open_only: bool = Query(True)) -> dict:
    reports = cf.open_reports() if open_only else cf.load_reports()
    return {
        "count": len(reports),
        "failures": [
            {
                "failure_id": r.failure_id,
                "error_class": r.error_class,
                "stage": r.stage,
                "source": r.source,
                "message": r.message,
                "log_excerpt": r.log_excerpt,
                "first_occurrence": r.first_occurrence,
                "last_occurrence": r.last_occurrence,
                "occurrence_count": r.occurrence_count,
                "status": r.status,
            }
            for r in reports
        ],
    }
