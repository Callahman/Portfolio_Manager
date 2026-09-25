"""Session runtime (Epic 5 DoD + Epic 10 ad-hoc sessions).

A session:
  1. selects roles — ad-hoc via --roles, or the Team Lead forms pods from
     all available roles (alternates by construction)
  2. runs bounded rounds of pod deliberation: each role speaks in its pod's
     shared conversation, the pod lead synthesizes the pod decision, and the
     Team Lead relays each pod's decision into the next pod's context
     (deterministic relay). Inter-round context is bounded (team/context.py).
  3. after each round the Team Lead may close early (convergence check)
  4. final: the Portfolio Manager proposes the allocation, the Team Lead
     synthesizes the final recommendation
  5. writes the transcript (JSONL + markdown) and, when posted, the decision
     journal (common/history.py)
  6. optionally posts the final recommendation to the 1080 API (--post)

CLI:
  python -m team.session [--roles r1,r2,...] [--rounds 3] [--post]
                         [--session-id ID] [--api-base URL]

Exit codes: 0 = completed, 1 = error, 2 = session timeout.
"""
from __future__ import annotations

import json
import logging
import random
import sys
import time

import requests

from common import config
from common import history as chist
from team import context as tcontext
from team import invocation
from team import pods as tpods
from team import roles as troles
from team.roles import get_role

log = logging.getLogger(__name__)

AGENDA = (
    "Daily portfolio deliberation: review the market snapshot, statistical "
    "signals, fundamentals, macro readings, and risk metrics; weigh the "
    "counter-evidence; converge on a recommendation within the risk policy."
)


class SessionTimeout(RuntimeError):
    pass


def _check_timeout(start: float, timeout_s: float, session_id: str) -> None:
    if time.time() - start > timeout_s:
        chist.append_entry(
            session_id,
            {"role": "system", "pod": "-", "content": {"summary": "SESSION TIMEOUT — aborting"}, "ts": time.time()},
        )
        raise SessionTimeout(f"session {session_id} exceeded {timeout_s / 3600:.1f}h")


def _relay_context(base_context: str, prior_decisions: list[dict]) -> str:
    if not prior_decisions:
        return base_context
    return (
        base_context
        + "\n\nPREVIOUS POD DECISIONS (relayed by the Team Lead):\n"
        + json.dumps(prior_decisions, indent=2)
    )


def _lead_feed_with_decisions(lead_feed: dict, decisions: list[dict], pm_out: dict | None = None) -> dict:
    feed = dict(lead_feed) if lead_feed else {"role": "team_lead", "data": {}}
    data = dict(feed.get("data") or {})
    data["pod_decisions"] = decisions
    if pm_out:
        data["portfolio_manager_allocation"] = pm_out
    feed["data"] = data
    return feed


def run_session(roles_arg: str | None, rounds: int, post: bool, session_id: str, api_base: str | None) -> int:
    config.load_env()
    start = time.time()
    timeout_s = config.get_float("SESSION_TIMEOUT_HOURS", 4.0) * 3600
    max_rounds = config.get_int("DELIBERATION_MAX_ROUNDS", 6)
    rounds = max(1, min(rounds, max_rounds))

    chist.start_session(
        session_id, meta={"roles_arg": roles_arg, "rounds": rounds, "post": post}
    )
    chist.append_entry(
        session_id,
        {
            "role": "system",
            "pod": "-",
            "content": {"summary": f"session start: rounds={rounds}, roles={roles_arg or 'team-lead formation'}"},
            "ts": time.time(),
        },
    )

    # 1. pods
    if roles_arg:
        selected = [r.strip() for r in roles_arg.split(",") if r.strip()]
        for r in selected:
            get_role(r)  # raises KeyError on unknown role
        pods = tpods.chunk_roles(selected)
        chist.append_entry(
            session_id,
            {"role": "system", "pod": "-", "content": {"summary": f"ad-hoc pods: {[(p.name, p.roles) for p in pods]}"}, "ts": time.time()},
        )
    else:
        available = [r for r in troles.all_roles() if r != "team_lead"]
        pods = tpods.form_pods(available, api_base)
        chist.append_entry(
            session_id,
            {"role": "system", "pod": "-", "content": {"summary": f"Team Lead formed pods: {[(p.name, p.roles) for p in pods]}"}, "ts": time.time()},
        )
    if not pods:
        log.error("no pods to run")
        return 1

    # base digest: the Team Lead's quality brief
    lead_feed: dict = {}
    try:
        lead_feed = invocation.fetch_feed("team_lead", api_base)
        digest = {"quality": lead_feed.get("quality"), "as_of": lead_feed.get("as_of")}
    except Exception as e:
        log.warning("team_lead feed unavailable (%s) — running without the quality brief", e)
        digest = {}

    round_summaries: list[str] = []
    final_rec: dict | None = None

    # 2. rounds
    for rnd in range(1, rounds + 1):
        _check_timeout(start, timeout_s, session_id)
        base_context = tcontext.assemble_context(
            agenda=AGENDA, round_summaries=round_summaries, digests=digest
        )
        chist.append_entry(
            session_id,
            {"role": "system", "pod": "-", "content": {"summary": f"round {rnd}/{rounds} start"}, "ts": time.time()},
        )
        prior_decisions: list[dict] = []
        round_entries: list[dict] = []
        for pod in pods:
            _check_timeout(start, timeout_s, session_id)
            relay = _relay_context(base_context, prior_decisions)
            tpods.run_pod(pod, agenda=AGENDA, context=relay, api_base=api_base)
            for e in pod.entries:
                round_entries.append(e)
                chist.append_entry(session_id, {**e, "round": rnd})
            if pod.decision:
                prior_decisions.append(pod.decision)
        round_summaries.append(tcontext.summarize_round(round_entries))

        # convergence check (Team Lead may close early)
        if rnd < rounds:
            _check_timeout(start, timeout_s, session_id)
            extra = (
                "PHASE: convergence check. The team has completed round "
                f"{rnd}/{rounds}. Has the team converged enough to stop? If yes, set "
                "`close: true` and provide `final_recommendation`. If not, set "
                "`close: false` and summarize what is still open in `summary`."
            )
            try:
                res = invocation.invoke_role(
                    "team_lead",
                    api_base=api_base,
                    feed=_lead_feed_with_decisions(lead_feed, prior_decisions),
                    extra_instructions=extra,
                )
                out = res["output"]
                chist.append_entry(
                    session_id, {"role": "team_lead", "pod": "-", "round": rnd, "content": out, "ts": time.time()}
                )
                if out.get("close") and out.get("final_recommendation"):
                    final_rec = out["final_recommendation"]
                    log.info("Team Lead closed the session after round %d", rnd)
                    break
            except Exception as e:
                log.warning("convergence check failed (%s) — continuing to the next round", e)

    # 3. final
    if final_rec is None:
        _check_timeout(start, timeout_s, session_id)
        all_decisions = [p.decision for p in pods if p.decision]
        pm_extra = (
            "PHASE: final allocation. Propose the concrete allocation actions "
            "(buy/sell, tickers, shares) from the team's pod decisions. Each "
            "action must carry its rationale and respect the risk policy."
        )
        pm_out: dict = {}
        try:
            res = invocation.invoke_role(
                "portfolio_manager", api_base=api_base, extra_instructions=pm_extra
            )
            pm_out = res["output"]
            chist.append_entry(
                session_id, {"role": "portfolio_manager", "pod": "-", "content": pm_out, "ts": time.time()}
            )
        except Exception as e:
            log.error("portfolio_manager failed (%s) — Team Lead synthesizes from pod decisions only", e)
        lead_extra = (
            "PHASE: final synthesis. Synthesize the team's final recommendation "
            "from the pod decisions and the Portfolio Manager's allocation. Put it "
            "in `final_recommendation` (actions + rationale). It must be concrete, "
            "affordable, and within the risk policy."
        )
        try:
            res = invocation.invoke_role(
                "team_lead",
                api_base=api_base,
                feed=_lead_feed_with_decisions(lead_feed, all_decisions, pm_out),
                extra_instructions=lead_extra,
            )
            out = res["output"]
            chist.append_entry(
                session_id, {"role": "team_lead", "pod": "-", "content": out, "ts": time.time()}
            )
            final_rec = out.get("final_recommendation")
        except Exception as e:
            log.error("Team Lead final synthesis failed: %s", e)
    if final_rec is None:
        log.error("no final recommendation produced")
        chist.write_markdown(session_id)
        return 1

    # 4. post + decision journal
    if post:
        rec_payload = {
            "actions": final_rec.get("actions", []),
            "rationale": final_rec.get("rationale", ""),
        }
        base = (api_base or config.get("FEED_API_BASE") or "").rstrip("/")
        try:
            r = requests.post(f"{base}/recommendation", json=rec_payload, timeout=120)
            result = {"status_code": r.status_code, "body": r.json() if r.ok else r.text[:500]}
            chist.record_decision(session_id, rec_payload, result)
            chist.append_entry(
                session_id,
                {"role": "system", "pod": "-", "content": {"summary": f"posted recommendation: HTTP {r.status_code}"}, "ts": time.time()},
            )
        except Exception as e:
            result = {"error": str(e)}
            chist.record_decision(session_id, rec_payload, result)
            log.error("POST /recommendation failed: %s", e)

    chist.write_markdown(session_id)
    chist.prune()
    log.info(
        "session %s complete: %d rounds, final recommendation with %d actions",
        session_id, rounds, len(final_rec.get("actions", [])),
    )
    return 0


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    roles_arg: str | None = None
    rounds = 3
    post = False
    session_id: str | None = None
    api_base: str | None = None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--roles":
            roles_arg = argv[i + 1]
            i += 2
        elif a == "--rounds":
            rounds = int(argv[i + 1])
            i += 2
        elif a == "--post":
            post = True
            i += 1
        elif a == "--session-id":
            session_id = argv[i + 1]
            i += 2
        elif a == "--api-base":
            api_base = argv[i + 1]
            i += 2
        else:
            log.error("unknown argument: %s", a)
            return 1
    if session_id is None:
        session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + "".join(
            random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=4)
        )
    code = 1
    try:
        code = run_session(roles_arg, rounds, post, session_id, api_base)
    except SessionTimeout as e:
        log.error("%s", e)
        code = 2
    except (KeyError, ValueError, requests.RequestException) as e:
        log.error("%s", e)
        code = 1
    try:
        from team import health as thealth

        thealth.record_session(session_id, "completed" if code == 0 else f"exit {code}")
    except Exception:
        pass
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
