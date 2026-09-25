"""Economist role (Epic 5, Story 5.1).

Data tier: derived (macro readings feed). Edit scope: analyze/.
The Economist interprets the macro environment and forms a policy outlook;
the final portfolio call belongs to the Team Lead / Portfolio Manager.
"""
from team.roles.base import base_schema, make_role

ROLE = make_role(
    name="economist",
    title="Economist",
    mandate=(
        "You are the Economist on the Portfolio Manager team. "
        "You interpret the macro environment: rates, inflation, labor market, "
        "sentiment, and policy news. You form a policy outlook — what the Fed and "
        "the data imply for the next few months — and its implications for the "
        "assets in the watchlist. You work only from the macro readings, upcoming "
        "releases, and policy news in the feed; every number you cite must come "
        "from the feed. You do not make final portfolio calls — you inform the "
        "Team Lead and the Portfolio Manager."
    ),
    input_spec=(
        "macro_readings: per-series value, 1p/12p changes, frequency, last 6 "
        "observations; upcoming releases; policy news headlines"
    ),
    output_schema=base_schema(
        "economist",
        extra_props={
            "policy_outlook": {"type": "string"},
            "upcoming_events": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        extra_required=["policy_outlook"],
    ),
)
