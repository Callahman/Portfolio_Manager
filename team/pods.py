"""Pod manager (Epic 5, Story 5.3; shared with ad-hoc sessions, Epic 10).

Pods are 2-3 roles deliberating in their own conversation (no cross-pod
spillover). The Team Lead forms pods from the available roles (alternates
by construction: unavailable roles are simply not offered); deterministic
chunking is the fallback when the LLM formation is invalid. The Team Lead
relays each pod's decision into the next pod's context (done by the session
runtime, deterministically).

A pod's turn (run_pod):
  1. each role speaks in turn (structured output, shared pod conversation)
  2. the pod's lead role (first in the list) synthesizes the pod decision
     {decision, rationale, confidence, evidence}
"""
from __future__ import annotations

import logging
import time

from team import invocation

log = logging.getLogger(__name__)

POD_MIN_ROLES = 2
POD_MAX_ROLES = 3
MAX_PODS = 5


class Pod:
    def __init__(self, name: str, roles: list[str]):
        self.name = name
        self.roles = roles
        self.entries: list[dict] = []
        self.decision: dict | None = None

    def add_entry(self, role: str, content) -> None:
        self.entries.append({"role": role, "pod": self.name, "content": content, "ts": time.time()})


def chunk_roles(roles: list[str], max_per_pod: int = POD_MAX_ROLES) -> list[Pod]:
    """Deterministic fallback formation: consecutive chunks of <= max_per_pod;
    a lone tail is merged into the previous pod if it fits."""
    pods: list[Pod] = []
    for i in range(0, len(roles), max_per_pod):
        chunk = roles[i : i + max_per_pod]
        if len(chunk) < POD_MIN_ROLES and pods and len(pods[-1].roles) + len(chunk) <= max_per_pod:
            pods[-1].roles.extend(chunk)
        else:
            pods.append(Pod(f"pod_{len(pods) + 1}", chunk))
    return pods


def _validate_formation(pods_out: list[dict], available: list[str]) -> list[Pod] | None:
    """Deterministic validation of the Team Lead's formation. Returns None if
    the formation is unusable (the caller falls back to chunking)."""
    names = set(available)
    pods: list[Pod] = []
    seen: set[str] = set()
    for i, p in enumerate(pods_out[:MAX_PODS]):
        roles = [r for r in p.get("roles", []) if r in names]
        roles = [r for r in dict.fromkeys(roles) if r not in seen]
        seen.update(roles)
        if not roles:
            return None
        if len(roles) > POD_MAX_ROLES:
            roles = roles[:POD_MAX_ROLES]
        pods.append(Pod(p.get("name") or f"pod_{i + 1}", roles))
    return pods or None


def form_pods(available_roles: list[str], api_base: str | None = None) -> list[Pod]:
    """Team Lead forms pods from the available roles. Falls back to
    deterministic chunking if the formation output is invalid."""
    if not available_roles:
        return []
    formation_extra = (
        "PHASE: pod formation. Form the pods for this session from the AVAILABLE "
        f"ROLES below. Rules: 2-3 roles per pod (one role only if that is all that "
        f"is available), at most {MAX_PODS} pods, every available role used at most "
        f"once, group roles that inform each other. Respond with the `pods` field "
        f"of your schema.\nAVAILABLE ROLES: {', '.join(available_roles)}"
    )
    try:
        feed = invocation.fetch_feed("team_lead", api_base)
    except Exception as e:
        log.warning("team_lead feed unavailable (%s) — using deterministic formation", e)
        return chunk_roles(available_roles)
    try:
        res = invocation.invoke_role(
            "team_lead", api_base=api_base, feed=feed, extra_instructions=formation_extra
        )
        pods = _validate_formation(res["output"].get("pods", []), available_roles)
        if pods is None:
            raise ValueError("invalid formation output")
        log.info("Team Lead formed %d pods: %s", len(pods), [(p.name, p.roles) for p in pods])
        return pods
    except Exception as e:
        log.warning("LLM pod formation failed (%s) — falling back to deterministic chunking", e)
        return chunk_roles(available_roles)


def run_pod(pod: Pod, *, agenda: str, context: str, api_base: str | None = None) -> Pod:
    """One pod turn: each role speaks in the shared pod conversation, then the
    pod lead (first role) synthesizes the pod decision."""
    for i, role in enumerate(pod.roles):
        extra = (
            f"PHASE: pod deliberation, pod {pod.name}, speaker {i + 1}/{len(pod.roles)} "
            f"of this round. You are speaking in a shared pod conversation with: "
            f"{', '.join(pod.roles)}. Build on what your pod-mates said; do not repeat "
            f"them. Speak only within your mandate.\n\nSESSION CONTEXT:\n{context}"
        )
        try:
            res = invocation.invoke_role(role, api_base=api_base, extra_instructions=extra)
            pod.add_entry(role, res["output"])
        except Exception as e:
            log.error("role %s failed in pod %s: %s", role, pod.name, e)
            pod.add_entry(role, {"summary": f"(role unavailable: {e})", "error": str(e)})
    # pod decision: the lead synthesizes
    lead = pod.roles[0]
    extra = (
        f"PHASE: pod decision. You are the lead of pod {pod.name}. Synthesize the "
        f"pod's decision from the pod conversation. Put the decision in your "
        f"`recommendation` field and the synthesis in `summary`."
    )
    try:
        res = invocation.invoke_role(lead, api_base=api_base, extra_instructions=extra)
        out = res["output"]
        pod.decision = {
            "pod": pod.name,
            "decision": out.get("recommendation", ""),
            "rationale": out.get("summary", ""),
            "confidence": out.get("confidence"),
            "evidence": out.get("findings", []),
        }
        pod.add_entry(lead, {"summary": f"POD DECISION: {pod.decision['decision']}"})
    except Exception as e:
        log.error("pod decision synthesis failed for %s: %s", pod.name, e)
        first = pod.entries[0] if pod.entries else None
        content = first.get("content") if first else None
        pod.decision = {
            "pod": pod.name,
            "decision": (content.get("recommendation") if isinstance(content, dict) else str(content) or ""),
            "rationale": "lead synthesis unavailable — using first speaker's recommendation",
            "confidence": None,
            "evidence": [],
        }
    return pod
