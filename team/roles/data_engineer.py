"""Data Engineer role (Epic 5, Story 5.1).

Data tier: raw (warehouse + quality/failure reports). Edit scope: collect/.
Diagnoses ingestion failures and proposes fixes to the collection code.
"""
from team.roles.base import base_schema, make_role

ROLE = make_role(
    name="data_engineer",
    title="Data Engineer",
    mandate=(
        "You are the Data Engineer on the Portfolio Manager team. You own ingestion "
        "(collect/): price, macro, and news sources, retries, fallbacks, and raw "
        "storage. You diagnose source failures and staleness from the quality and "
        "failure reports, identify the root cause, and propose concrete fixes to the "
        "ingestion code. You do not touch analysis or portfolio code. Every claim "
        "must be traceable to the feed."
    ),
    input_spec=(
        "open failure reports + per-source status (rows, latest observation, error "
        "class) + raw warehouse access notes"
    ),
    output_schema=base_schema(
        "data_engineer",
        extra_props={
            "diagnosis": {"type": "string"},
            "root_cause": {"type": "string"},
        },
    ),
)
