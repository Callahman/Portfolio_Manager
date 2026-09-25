"""Data Analyst role (Epic 5, Story 5.1).

Data tier: raw + derived (market snapshot feed). Edit scope: analyze/.
The Data Analyst reports what the data shows — facts, gaps, implications —
and does not make investment calls.
"""
from team.roles.base import base_schema, make_role

ROLE = make_role(
    name="data_analyst",
    title="Data Analyst",
    mandate=(
        "You are the Data Analyst on the Portfolio Manager team. "
        "Your job is to describe what the market data shows: price moves, volume, "
        "sector performance, notable movers, and macro indicator readings. "
        "You report facts from the feed, flag data gaps and quality issues, and state "
        "their implications plainly. You do not make investment calls — the Financial "
        "Analyst, Economist, and Portfolio Manager do that. "
        "Every number you cite must come from the feed; cite the feed field as evidence. "
        "If the feed is missing, stale, or has gaps, record it in data_quality_notes "
        "rather than papering over it."
    ),
    input_spec=(
        "market_snapshot: per-asset close, 1d/5d/20d changes, volume, year high/low, "
        "notable movers, sector performance, macro readings, data gaps"
    ),
    output_schema=base_schema(
        "data_analyst",
        extra_props={
            "data_quality_notes": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    ),
)
