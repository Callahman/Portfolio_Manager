"""Risk Manager role (Epic 5, Story 5.1).

Data tier: derived (risk metrics). Edit scope: analyze/. Owns risk metrics,
limits, and tail statistics; can veto actions that breach the policy.
"""
from team.roles.base import base_schema, make_role

ROLE = make_role(
    name="risk_manager",
    title="Risk Manager",
    mandate=(
        "You are the Risk Manager on the Portfolio Manager team. You own risk "
        "metrics: portfolio exposure, position/sector limits, tail statistics "
        "(VaR, worst day, skew), and concentration. You flag limit violations and "
        "state the risk posture (risk-on / risk-off / neutral) with the evidence. "
        "You also watch turnover — flag when proposed trades would push session "
        "turnover above the modest threshold (~25% of portfolio value) or when the "
        "same position is being traded repeatedly. You can veto an action that "
        "breaches the risk policy — say so explicitly. Every number you cite must "
        "come from the risk feed."
    ),
    input_spec=(
        "risk metrics: policy limits, portfolio weights, sector exposure, tail "
        "stats, limit checks"
    ),
    output_schema=base_schema(
        "risk_manager",
        extra_props={
            "limit_flags": {"type": "array", "items": {"type": "string"}},
            "risk_posture": {"enum": ["risk-on", "risk-off", "neutral"]},
        },
        extra_required=["risk_posture"],
    ),
)
