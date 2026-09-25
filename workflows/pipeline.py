"""Daily pipeline (Epic 7, Story 7.1) — the 1080's canonical run.

Stages (sequential; a failed stage halts the run, records the failure, and
emails it):
  collect_prices  python -m collect.runner prices
  collect_macro   python -m collect.runner macro
  collect_news    python -m collect.runner news
  validate        python -m validate.runner
  analyze         python -m analyze.runner
  portfolio_mark  python -m portfolio.metrics mark
  deliver         report + email (in-process)
  archive         today's outputs -> archives/{date}/ (in-process)

Stage tracking: history/pipeline/state.json (started_at, per-stage status,
exit codes, errors, finished_at).

Usage:
  python -m workflows.pipeline [--stages collect_prices,validate,...]
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

from common import config

log = logging.getLogger(__name__)

STATE_PATH = config.HISTORY_DIR / "pipeline" / "state.json"

STAGES: list[tuple[str, list[str] | None]] = [
    ("collect_prices", ["-m", "collect.runner", "prices"]),
    ("collect_macro", ["-m", "collect.runner", "macro"]),
    ("collect_news", ["-m", "collect.runner", "news"]),
    ("validate", ["-m", "validate.runner"]),
    ("analyze", ["-m", "analyze.runner"]),
    ("portfolio_mark", ["-m", "portfolio.metrics", "mark"]),
    ("deliver", None),  # in-process
    ("archive", None),  # in-process
]


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _write_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _prior_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _resume_stages() -> list[str] | None:
    """Return the stage names to skip (already completed ok in a prior
    same-day halted run), or None if there is nothing to resume from.

    This makes the pipeline resumable: a failed run restarted on the same day
    picks up from the last completed stage instead of re-running everything.
    """
    prior = _prior_state()
    if not prior or prior.get("status") != "failed":
        return None
    if prior.get("day") != _day():
        return None  # only resume same-day halted runs
    completed = [s["name"] for s in prior.get("stages", []) if s.get("status") == "ok"]
    if not completed:
        return None
    log.info("resuming same-day halted run; skipping completed stages: %s", ", ".join(completed))
    return completed


def _run_deliver() -> int:
    from delivery import email, report

    p = report.write_report()
    md = p.read_text(encoding="utf-8")
    email.send_run_summary(md)
    try:
        from common import failures as cf

        open_f = [
            {"failure_id": r.failure_id, "source": r.source, "message": r.message}
            for r in cf.open_reports()
        ]
        if open_f:
            email.send_failure_summary(open_f)
    except Exception as e:
        log.warning("failure email failed: %s", e)
    return 0


def _run_archive() -> int:
    day = _day()
    dst = config.ARCHIVES_DIR / day
    dst.mkdir(parents=True, exist_ok=True)
    for name, src in (
        ("raw", config.RAW_DIR),
        ("validated", config.VALIDATED_DIR),
        ("analytics", config.ANALYTICS_DIR),
    ):
        if src.is_dir():
            shutil.copytree(src, dst / name, dirs_exist_ok=True)
    rep = config.REPORTS_DIR / f"{day}.md"
    if rep.exists():
        shutil.copy2(rep, dst / "report.md")
    log.info("archived today's outputs to %s", dst)
    return 0


def run(stages: list[str] | None = None) -> int:
    config.load_env()
    selected = [s for s, _ in STAGES if stages is None or s in stages]
    resume = _resume_stages() if stages is None else None
    state = {
        "started_at": time.time(),
        "day": _day(),
        "stages": [],
        "status": "running",
        "current_stage": None,
        "error": "",
        "finished_at": None,
        "resumed": bool(resume),
    }
    _write_state(state)
    for name, cmd in STAGES:
        if name not in selected:
            continue
        if resume and name in resume:
            state["stages"].append({
                "name": name, "status": "ok", "exit_code": 0, "error": "",
                "resumed_from_prior_run": True,
                "started_at": time.time(), "finished_at": time.time(),
            })
            _write_state(state)
            log.info("skipping stage %s (completed in prior run)", name)
            continue
        state["current_stage"] = name
        _write_state(state)
        entry = {"name": name, "started_at": time.time(), "status": "running", "exit_code": None, "error": ""}
        try:
            if cmd is not None:
                r = subprocess.run([sys.executable, *cmd], capture_output=True, text=True, timeout=3600)
                entry["exit_code"] = r.returncode
                if r.returncode != 0:
                    entry["error"] = (r.stderr or r.stdout or "")[-2000:]
            else:
                rc = _run_deliver() if name == "deliver" else _run_archive()
                entry["exit_code"] = rc
        except Exception as e:
            entry["exit_code"] = None
            entry["error"] = str(e)
        entry["finished_at"] = time.time()
        entry["status"] = "ok" if entry["exit_code"] == 0 else "failed"
        state["stages"].append(entry)
        _write_state(state)
        if entry["status"] != "ok":
            state["status"] = "failed"
            state["error"] = f"stage {name} failed: {entry['error'][:500]}"
            state["finished_at"] = time.time()
            _write_state(state)
            log.error("pipeline HALTED at stage %s: %s", name, entry["error"][:500])
            try:
                from delivery import dispatch

                dispatch.after_run_failure(
                    f"pipeline stage {name} failed (exit {entry['exit_code']})\n{entry['error'][:2000]}"
                )
            except Exception as e:
                log.warning("failure email failed: %s", e)
            return 1
    state["status"] = "ok"
    state["current_stage"] = None
    state["finished_at"] = time.time()
    _write_state(state)
    log.info("pipeline complete: %d stages ok", len(state["stages"]))
    return 0


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stages = None
    i = 1
    while i < len(argv):
        if argv[i] == "--stages":
            stages = [s.strip() for s in argv[i + 1].split(",") if s.strip()]
            i += 2
        else:
            log.error("unknown argument: %s", argv[i])
            return 1
    return run(stages)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
