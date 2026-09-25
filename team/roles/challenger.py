"""Challenger role (Epic 5, Story 5.1).

Data tier: derived (counter-evidence). Edit scope: analyze/. The
counter-evidence role: steelmans the bear case and attacks the team's
strongest assumptions.
"""
from team.roles.base import base_schema, make_role

ROLE = make_role(
    name="challenger",
    title="Challenger",
    mandate=(
        "You are the Challenger on the Portfolio Manager team. Your job is "
        "counter-evidence: you steelman the bear case, attack the team's strongest "
        "assumptions, and surface what the digests downplay (drawdowns, negative "
        "momentum, high volatility, limit violations, data gaps). You argue from "
        "the feed — every counter-argument must cite evidence. You do not propose "
        "the final allocation; you make the team's case survive contact with its "
        "weakest points."
    ),
    input_spec=(
        "counter-evidence: bearish signals, limit violations, tail stats, data "
        "gaps"
    ),
    output_schema=base_schema(
        "challenger",
        extra_props={
            "counter_arguments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["argument", "evidence"],
                    "properties": {
                        "argument": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                },
            },
        },
        extra_required=["counter_arguments"],
    ),
)
