"""Structured failure reports — the contract between the 1080's pipeline
and the 4090's role-scoped self-modification loop (outline §2.9).

A failure report carries: error class, stage, source, message, log excerpt,
first/last occurrence, occurrence count, status. Reports are JSON files in
`validate/validated/failures/` and are exposed via `GET /failures`.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

FAILURE_DIR_DEFAULT = Path(__file__).resolve().parent.parent / "validate" / "validated" / "failures"


def new_failure_id() -> str:
    return "F-" + uuid.uuid4().hex[:8]


@dataclass
class FailureReport:
    failure_id: str
    error_class: str          # e.g. fetch_http_error, schema_mismatch, stale_data, config_missing
    stage: str                # collect | validate | analyze | portfolio | delivery
    source: str               # e.g. prices:yahoo:SPY, macro:fred:DFF, news:rss:topstories
    message: str
    log_excerpt: str = ""
    first_occurrence: float = field(default_factory=time.time)
    last_occurrence: float = field(default_factory=time.time)
    occurrence_count: int = 1
    status: str = "open"      # open | fixed | reverted | escalated

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "FailureReport":
        return cls(**json.loads(text))


def report_path(failure_id: str, directory: Path | None = None) -> Path:
    d = directory or FAILURE_DIR_DEFAULT
    return d / f"{failure_id}.json"


def save_report(report: FailureReport, directory: Path | None = None) -> Path:
    d = directory or FAILURE_DIR_DEFAULT
    d.mkdir(parents=True, exist_ok=True)
    p = report_path(report.failure_id, d)
    p.write_text(report.to_json(), encoding="utf-8")
    return p


def load_reports(directory: Path | None = None) -> list[FailureReport]:
    d = directory or FAILURE_DIR_DEFAULT
    if not d.is_dir():
        return []
    out: list[FailureReport] = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(FailureReport.from_json(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def open_reports(directory: Path | None = None) -> list[FailureReport]:
    return [r for r in load_reports(directory) if r.status == "open"]


def find_by_source(source: str, directory: Path | None = None) -> Optional[FailureReport]:
    """Find an open report for the same source (for occurrence counting)."""
    for r in open_reports(directory):
        if r.source == source:
            return r
    return None
