"""Role-scoped self-modification loop (Epic 9) — runs on the 4090, nightly.

Reads the open failure reports from the 1080, groups them by the failure
source, and asks the owning role for a concrete fix. Scope is enforced by
construction (outline §2.9):

  prices/macro/news failures -> data_engineer -> collect/ only

A fix is applied only if every changed path is inside the role's scope and
the tree still passes the smoke test (workflows.smoketest). On failure the
changes are reverted and the escalation counter increments; at
SELF_MOD_MAX_ESCALATIONS the loop stops and emails. A successful fix resets
the counter.

CLI:
  python -m team.self_mod [--dry-run] [--max-groups N] [--api-base URL]
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import requests

from common import config
from team import invocation

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]

# failure source prefix -> (role, allowed path prefixes, files offered as context)
SCOPE = {
    "prices": ("data_engineer", ("collect/",), ["collect/prices.py", "collect/raw_store.py", "collect/runner.py"]),
    "macro": ("data_engineer", ("collect/",), ["collect/macro_fred.py", "collect/raw_store.py", "collect/runner.py"]),
    "news": ("data_engineer", ("collect/",), ["collect/news_rss.py", "collect/raw_store.py", "collect/runner.py"]),
}

FIX_SCHEMA = {
    "type": "object",
    "required": ["role", "summary", "changes", "rationale"],
    "properties": {
        "role": {"type": "string"},
        "summary": {"type": "string"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
        "rationale": {"type": "string"},
        "risk": {"type": "string"},
    },
}

ESCALATION_PATH = config.HISTORY_DIR / "self_mod" / "escalations.json"


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr[:500]}")
    return r.stdout.strip()


def _escalations() -> int:
    if not ESCALATION_PATH.exists():
        return 0
    try:
        return int(json.loads(ESCALATION_PATH.read_text(encoding="utf-8")).get("count", 0))
    except (json.JSONDecodeError, ValueError):
        return 0


def _set_escalations(n: int) -> None:
    ESCALATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    ESCALATION_PATH.write_text(json.dumps({"count": n, "ts": time.time()}), encoding="utf-8")


def _notify(subject: str, body: str) -> None:
    try:
        from delivery import email

        email.send(subject, body)
    except Exception as e:
        log.warning("notify failed: %s", e)


def _open_failures(api_base: str | None) -> list[dict]:
    base = (api_base or config.get("FEED_API_BASE") or "").rstrip("/")
    if not base:
        raise ValueError("no 1080 API base — set FEED_API_BASE")
    r = requests.get(f"{base}/failures", timeout=30)
    r.raise_for_status()
    return r.json().get("failures", [])


def _group_by_scope(failures: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for f in failures:
        source = f.get("source", "")
        for prefix in SCOPE:
            if source.startswith(prefix + ":"):
                groups.setdefault(prefix, []).append(f)
                break
    return groups


def _file_context(files: list[str], clip: int = 4000) -> str:
    parts = []
    for rel in files:
        p = REPO_ROOT / rel
        if p.exists():
            text = p.read_text(encoding="utf-8")
            parts.append(f"=== {rel} ===\n{text[:clip]}")
    return "\n\n".join(parts)


def _run_smoke() -> bool:
    r = subprocess.run(
        [sys.executable, "-m", "workflows.smoketest"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
    )
    return r.returncode == 0


def _fix_group(prefix: str, failures: list[dict], api_base: str | None, dry_run: bool) -> bool:
    """Ask the owning role for a fix. Returns True if the fix was applied (or
    dry-run-validated). Raises on scope violations or smoke failure."""
    role, prefixes, context_files = SCOPE[prefix]
    extra = (
        "PHASE: self-modification fix. An open failure report is below. Propose a "
        "concrete fix to the ingestion code. Rules:\n"
        f"- You may only change files under: {', '.join(prefixes)}\n"
        "- For each file you change, provide its FULL new content in `content`.\n"
        "- Do not change behavior beyond the fix; keep the module importable.\n\n"
        f"OPEN FAILURE REPORTS:\n{json.dumps(failures, indent=2)}\n\n"
        f"CURRENT CODE:\n{_file_context(context_files)}"
    )
    res = invocation.invoke_role(
        role, api_base=api_base, extra_instructions=extra, output_schema=FIX_SCHEMA
    )
    out = res["output"]
    changes = out.get("changes", [])
    if not changes:
        log.info("%s proposed no changes for %d failures", role, len(failures))
        return False
    # scope enforcement
    for c in changes:
        path = c.get("path", "")
        if not any(path.startswith(pfx) for pfx in prefixes):
            raise PermissionError(f"fix path {path!r} outside role scope {prefixes}")
        if not (REPO_ROOT / path).exists():
            raise FileNotFoundError(f"fix path {path!r} does not exist in the repo")
        if not c.get("content"):
            raise ValueError(f"empty content for {path!r}")
    if dry_run:
        log.info("[dry-run] %s would change: %s", role, [c["path"] for c in changes])
        return True
    # apply + smoke + commit, or revert
    for c in changes:
        (REPO_ROOT / c["path"]).write_text(c["content"], encoding="utf-8")
    if not _run_smoke():
        for c in changes:
            _git("checkout", "--", c["path"])
        raise RuntimeError(f"smoke test failed after {role}'s fix — reverted")
    _git("add", "-A", "collect", "validate", "analyze")
    _git("commit", "-m", f"self-mod ({role}): {out.get('summary', 'fix')[:120]}")
    try:
        _git("push")
        log.info("%s fix committed and pushed: %s", role, [c["path"] for c in changes])
    except RuntimeError as e:
        log.warning("%s fix committed locally but push failed (1080 will pick it up once the remote works): %s", role, e)
    return True


def run(max_groups: int = 3, dry_run: bool = False, api_base: str | None = None) -> int:
    config.load_env()
    max_esc = config.get_int("SELF_MOD_MAX_ESCALATIONS", 3)
    if _escalations() >= max_esc:
        log.error("escalation budget exhausted (%d) — self-mod disabled until reset", _escalations())
        return 1
    failures = _open_failures(api_base)
    groups = _group_by_scope(failures)
    if not groups:
        log.info("no open failures in self-mod scope — nothing to do")
        return 0
    log.info("open failures by source: %s", {k: len(v) for k, v in groups.items()})
    ok = 0
    for prefix, fails in list(groups.items())[:max_groups]:
        role, _, _ = SCOPE[prefix]
        try:
            if _fix_group(prefix, fails, api_base, dry_run):
                ok += 1
                _set_escalations(0)
        except (PermissionError, FileNotFoundError, ValueError, RuntimeError) as e:
            log.error("self-mod fix for %s rejected: %s", role, e)
            n = _escalations() + 1
            _set_escalations(n)
            if n >= max_esc:
                _notify("Portfolio Manager — self-mod escalations exhausted", f"{role}: {e}")
                log.error("escalation budget exhausted — stopping and emailing")
                return 1
        except (invocation.InvocationError, requests.RequestException) as e:
            log.error("self-mod invocation for %s failed: %s", role, e)
    log.info("self-mod done: %d/%d groups fixed", ok, min(len(groups), max_groups))
    return 0


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    dry_run = False
    max_groups = 3
    api_base: str | None = None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            dry_run = True
            i += 1
        elif a == "--max-groups":
            max_groups = int(argv[i + 1])
            i += 2
        elif a == "--api-base":
            api_base = argv[i + 1]
            i += 2
        else:
            log.error("unknown argument: %s", a)
            return 1
    try:
        return run(max_groups=max_groups, dry_run=dry_run, api_base=api_base)
    except (ValueError, RuntimeError, requests.RequestException) as e:
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
