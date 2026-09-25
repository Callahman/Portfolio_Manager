"""Financial Analyst role (Epic 5, Story 5.1).

Data tier: derived (fundamentals + ticker news). Edit scope: analyze/.
Forms per-ticker views from free fundamental data.
"""
from team.roles.base import base_schema, make_role

ROLE = make_role(
    name="financial_analyst",
    title="Financial Analyst",
    mandate=(
        "You are the Financial Analyst on the Portfolio Manager team. You analyze "
        "fundamentals from the free data: relative strength, price-range position, "
        "sector rotation, and ticker-specific news/events. You form per-ticker "
        "views and state what would change them. You work only from the "
        "fundamentals feed and ticker news; you do not make the final allocation "
        "call."
    ),
    input_spec=(
        "fundamentals: per-ticker price-range percentile, relative strength, "
        "events; sector rotation"
    ),
    output_schema=base_schema(
        "financial_analyst",
        extra_props={
            "ticker_views": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["ticker", "view"],
                    "properties": {
                        "ticker": {"type": "string"},
                        "view": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                },
            },
        },
    ),
)
