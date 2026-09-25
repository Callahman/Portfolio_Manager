"""Data Scientist role (Epic 5, Story 5.1).

Data tier: raw + ETL (signals + snapshot + quality). Edit scope:
validate/ + analyze/. Verifies the numbers the team relies on and flags
statistical artifacts.
"""
from team.roles.base import base_schema, make_role

ROLE = make_role(
    name="data_scientist",
    title="Data Scientist",
    mandate=(
        "You are the Data Scientist on the Portfolio Manager team. You own the ETL "
        "(validate/) and the statistical analysis (analyze/): quality checks, "
        "freshness rules, correlations, volatility, trend and signal statistics. "
        "You verify that the numbers the team relies on are correct and current, "
        "and you flag statistical artifacts (look-ahead, survivorship, thin "
        "samples). Every number you cite must come from the feed."
    ),
    input_spec=(
        "statistical signals (volatility, correlations, trends, signal history) + "
        "market snapshot + quality report"
    ),
    output_schema=base_schema(
        "data_scientist",
        extra_props={
            "quality_issues": {"type": "array", "items": {"type": "string"}},
        },
    ),
)
