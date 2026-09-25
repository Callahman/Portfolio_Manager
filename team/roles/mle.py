"""MLE role (Epic 5, Story 5.1).

Data tier: raw (signals + snapshot + workflow state). Edit scope:
workflows/ + analyze/. Owns algorithmic workflows: feature stores, model
training/serving, orchestration, monitoring.
"""
from team.roles.base import base_schema, make_role

ROLE = make_role(
    name="mle",
    title="MLE",
    mandate=(
        "You are the Machine Learning Engineer on the Portfolio Manager team. You "
        "own the algorithmic workflows (workflows/): feature stores, model "
        "training/serving, orchestration, and monitoring. You report on workflow "
        "health and model signal quality from the feeds, and you flag when a model "
        "output should not be trusted (drift, thin history, overfit signals). "
        "Every claim must be traceable to the feed."
    ),
    input_spec=(
        "statistical signals + signal history + market snapshot + workflow state "
        "notes"
    ),
    output_schema=base_schema(
        "mle",
        extra_props={
            "workflow_notes": {"type": "array", "items": {"type": "string"}},
        },
    ),
)
