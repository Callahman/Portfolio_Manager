"""Data quality report (Step 2) — machine-readable, per run.

Written to `validate/validated/quality.json` and exposed via `GET /quality`.
Covers: per-source status (ok/stale/failed), rows, latest observation,
freshness, and per-kind coverage (fraction of configured sources ok).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from common import config

VALIDATED_DIR = config.VALIDATED_DIR
QUALITY_PATH = VALIDATED_DIR / "quality.json"


def build_report(results: list[dict], failure_ids: list[str]) -> dict:
    by_kind: dict[str, list[dict]] = {}
    for r in results:
        by_kind.setdefault(r["kind"], []).append(r)

    sources = {r["source"]: r for r in results}
    coverage = {}
    for kind, rs in by_kind.items():
        ok = sum(1 for r in rs if r["status"] in ("ok",))
        coverage[kind] = round(ok / len(rs), 3) if rs else 1.0

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": sources,
        "coverage": coverage,
        "open_failure_ids": failure_ids,
        "summary": {
            "total_sources": len(results),
            "ok": sum(1 for r in results if r["status"] == "ok"),
            "stale": sum(1 for r in results if r["status"] == "stale"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
        },
    }


def write_report(report: dict) -> None:
    VALIDATED_DIR.mkdir(parents=True, exist_ok=True)
    QUALITY_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def load_report() -> dict | None:
    if not QUALITY_PATH.exists():
        return None
    return json.loads(QUALITY_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    rep = load_report()
    print(json.dumps(rep, indent=2) if rep else "no quality report yet")
