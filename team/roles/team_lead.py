"""Team Lead role (Epic 5, Story 5.1).

Data tier: briefs. The Team Lead orchestrates the session: forms pods from
the available roles (alternates), relays each pod's decision to the next
pod, and synthesizes the final recommendation. Phases (formation,
convergence check, final synthesis) are driven by the session runtime
(team/session.py) via extra_instructions.
"""
from team.roles.base import make_role

POD_ITEM = {
    "type": "object",
    "required": ["name", "roles"],
    "properties": {
        "name": {"type": "string"},
        "roles": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
}

FINAL_RECOMMENDATION = {
    "type": "object",
    "required": ["actions", "rationale"],
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["ticker", "side", "shares", "rationale"],
                "properties": {
                    "ticker": {"type": "string"},
                    "side": {"enum": ["buy", "sell"]},
                    "shares": {"type": "number", "minimum": 0},
                    "rationale": {"type": "string"},
                },
            },
        },
        "rationale": {"type": "string"},
    },
}

ROLE = make_role(
    name="team_lead",
    title="Team Lead",
    mandate=(
        "You are the Team Lead on the Portfolio Manager team. You orchestrate the "
        "deliberation: you form pods from the available roles, you relay each pod's "
        "decision to the next pod so the team builds on its own work, and you "
        "synthesize the final recommendation. You work from the briefs and the pods' "
        "decisions in the feed — do not invent numbers. You may close the session "
        "early when the team has converged. The final recommendation must be concrete "
        "(actions with tickers, sides, and shares) and within the risk policy."
    ),
    input_spec=(
        "briefs: market highlights, sector performance, data gaps, risk summary, "
        "plus the session phase context (available roles, pod decisions, round state)"
    ),
    output_schema={
        "type": "object",
        "required": ["role", "summary"],
        "properties": {
            "role": {"const": "team_lead"},
            "summary": {"type": "string"},
            "pods": {"type": "array", "items": POD_ITEM},
            "final_recommendation": FINAL_RECOMMENDATION,
            "close": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
)
