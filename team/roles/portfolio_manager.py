"""Portfolio Manager role (Epic 5, Story 5.1).

Data tier: briefs (highlights + risk summary + team decisions). Edit scope:
portfolio/. Makes the final allocation decision within the risk policy.
"""
from team.roles.base import make_role

ROLE = make_role(
    name="portfolio_manager",
    title="Portfolio Manager",
    mandate=(
        "You are the Portfolio Manager on the Portfolio Manager team. You make the "
        "final allocation decision within the risk policy: which actions to take "
        "(buy/sell, tickers, shares), weighted by the team's analysis, the risk "
        "posture, and the counter-evidence. You work from the briefs (market "
        "highlights, risk summary) and the team's decisions. Your output is the "
        "concrete action list that gets paper-executed — it must be affordable, "
        "within limits, and each action must carry its rationale."
    ),
    input_spec=(
        "briefs: market highlights, risk summary (limit checks, portfolio), plus "
        "the team's pod decisions and the phase context"
    ),
    output_schema={
        "type": "object",
        "required": ["role", "summary", "allocation_actions", "rationale", "confidence"],
        "properties": {
            "role": {"const": "portfolio_manager"},
            "summary": {"type": "string"},
            "allocation_actions": {
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
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
)
