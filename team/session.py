"""Team session (Epic 5, Story 5.3 + Epic 10) — the 4090's team runtime.

A session:
  1. fetches each role's feed from the 1080's read-only API
  2. forms pods (Team Lead decides, or a deterministic fallback)
  3. runs a bounded number of deliberation rounds (each pod speaks in turn,
     Team Lead relays prior decisions); closes early on convergence or a
     detected deadlock (two identical consecutive round summaries)
  4. synthesizes a final recommendation (Portfolio Manager, Team Lead
     fallback, and a conservative hold if both fail) so a recommendation is
     always produced
  5. records the full transcript in conversation history (per-pod JSONL +
     markdown)
  6. optionally posts the recommendation to the 1080 (POST /recommendation)

Usage:
  python -m team.session --rounds 3 [--post] [--session-id ...]
  python -m team.session --roles quant,challenger,risk_manager   # ad-hoc subset
  python -m team.session --goal "analyze the semiconductor sector"  # free-form
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from common import config
from common import history as chist
from team import context, invocation, pods, roles as team_roles

log = logging.getLogger(__name__)

AGENDA = (
    "Assess the current market for the watchlist (SPY, QQQ, TLT, GLD). "
    "Identify the highest-conviction opportunities and risks, weigh the "
    "counter-evidence, and recommend concrete portfolio actions (buy/sell, "
    "tickers, sizing) within the risk policy."
)


def run(rounds: int = 3, roles: list[str] | None = None, session_id: str | None = None,
        post: bool = False, api_base: str | None = None, goal: str | None = None) -> int:
    config.load_env()
    base = api_base or (config.get("FEED_API_BASE") or "").strip()
    sid = session_id or datetime.now(timezone.utc).strftime("adhoc-%Y%m%d-%H%M%S")
    agenda = goal or AGENDA
    t0 = time.time()

    if not base:
        log.error("FEED_API_BASE not set — cannot fetch feeds")
        return 1

    # 1. fetch feeds (only for the roles in this session)
    feed_roles = roles or team_roles.all_roles()
    feeds: dict[str, dict] = {}
    for role in feed_roles:
        try:
            f = invocation.fetch_feed(role, base)
            if f is not None:
                feeds[role] = f
        except Exception as e:
            log.warning("feed fetch failed for %s: %s", role, e)
    if not feeds:
        log.error("could not fetch any feeds from %s", base)
        return 1

    # 2. form pods (Team Lead decides; deterministic chunking fallback)
    available = list(feeds.keys())
    if roles:
        pod_groups = pods.chunk_roles(roles)  # a single ad-hoc pod of the chosen roles
    else:
        pod_groups = pods.form_pods(available, api_base=base)
        if not pod_groups:
            pod_groups = pods.chunk_roles(available)

    # 3. deliberation rounds (bounded; close on deadlock)
    digests: list[dict] = []
    prev_summary: str | None = None
    closed_early = False
    for rnd in range(1, rounds + 1):
        rnd_entries: list[dict] = []
        context_str = agenda
        for pod in pod_groups:
            pod = pods.run_pod(pod, agenda=agenda, context=context_str, api_base=base)
            decision = pod.decision or {}
            digests.append({"round": rnd, "pod": pod.name, "roles": pod.roles, "decision": decision})
            rnd_entries.append({"role": pod.name, "content": {"summary": decision.get("decision", "")}})
            if decision.get("decision"):
                context_str = f"{context_str}\n\nPOD {pod.name} DECISION: {decision['decision']}"
        summary = context.summarize_round(rnd_entries)
        log.info("round %d: %d pods; %s", rnd, len(rnd_entries), summary[:120])
        if prev_summary is not None and summary == prev_summary:
            log.warning("deadlock detected at round %d — closing", rnd)
            closed_early = True
            break
        prev_summary = summary

    # 4. final recommendation (always produced)
    synthesis_fallback = False
    final_rec: list = []
    final_rationale = ""
    final_extra = "PHASE: final synthesis. Produce the final portfolio recommendation."
    try:
        pm = invocation.invoke_role("portfolio_manager", api_base=base, extra_instructions=final_extra)
        final_rec = pm["output"].get("allocation_actions", []) or pm["output"].get("actions", [])
        final_rationale = pm["output"].get("rationale", "") or pm["output"].get("summary", "")
    except Exception as e:
        log.warning("portfolio_manager final synthesis failed: %s", e)
        try:
            lead = invocation.invoke_role("team_lead", api_base=base, extra_instructions=final_extra)
            final_rec = lead["output"].get("actions", []) or lead["output"].get("allocation_actions", [])
            final_rationale = lead["output"].get("rationale", "") or lead["output"].get("summary", "")
        except Exception as e2:
            log.warning("team_lead final synthesis failed: %s", e2)
            synthesis_fallback = True
            final_rationale = (
                "Final synthesis unavailable (Portfolio Manager and Team Lead "
                "both failed). Conservative hold: no trades this round."
            )

    # 5. record the transcript (per-pod JSONL + markdown)
    as_of = next(iter(feeds.values())).get("as_of")
    meta = {
        "session_id": sid,
        "kind": "adhoc" if roles else "full",
        "roles": available,
        "pods": [p.name for p in pod_groups],
        "rounds_run": len({d.get("round") for d in digests}),
        "closed_early": closed_early,
        "synthesis_fallback": synthesis_fallback,
        "agenda": agenda,
        "as_of": as_of,
        "duration_s": round(time.time() - t0, 1),
        "recommendation": final_rec,
    }
    chist.start_session(sid, meta)
    for d in digests:
        chist.append_entry(sid, d)
    chist.finalize_session(sid, {"recommendation": final_rec, "rationale": final_rationale})
    log.info("session %s recorded (%d entries, %d pods, %d rounds)", sid, len(digests), len(pod_groups), meta["rounds_run"])

    # 6. optionally post to the 1080
    if post:
        import requests

        feeds_as_of = {role: (f or {}).get("as_of") for role, f in feeds.items()}
        portfolio_baseline = _fetch_portfolio_baseline(base)
        try:
            r = requests.post(f"{base}/recommendation", json={"actions": final_rec, "rationale": final_rationale}, timeout=60)
            log.info("posted recommendation to 1080: HTTP %d", r.status_code)
            chist.record_decision(
                sid,
                {"actions": final_rec, "rationale": final_rationale},
                {"http_status": r.status_code, "body": r.text[:500]},
                feeds_as_of=feeds_as_of,
                portfolio_baseline=portfolio_baseline,
            )
        except Exception as e:
            log.error("failed to post recommendation: %s", e)
    return 0


def _fetch_portfolio_baseline(base: str) -> dict | None:
    """Capture the paper-portfolio P&L state from the 1080 API (baseline for
    the decision journal's subsequent-outcome linkage, Epic 7.5)."""
    import requests

    try:
        r = requests.get(f"{base}/metrics", timeout=15)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return None


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="run a team session")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--roles", default="", help="comma-separated role subset (ad-hoc)")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--post", action="store_true", help="post the recommendation to the 1080")
    ap.add_argument("--api-base", default=None)
    ap.add_argument("--goal", default=None, help="free-form goal/prompt (overrides the default agenda)")
    a = ap.parse_args(argv)
    roles = [r.strip() for r in a.roles.split(",") if r.strip()] or None
    return run(a.rounds, roles, a.session_id, a.post, a.api_base, a.goal)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
