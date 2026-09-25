"""Role-definition contract (Epic 5, Story 5.1).

A role definition is a plain dict:
  name          role key — matches the 1080's /feeds/{role} (analyze/feeds.py
                ROLE_META uses the same names)
  title         human-readable role name
  mandate       the role's job, boundaries, and data discipline (goes into
                the prompt as the role's system-level instruction)
  input_spec    one line: what the role's feed contains (for the prompt)
  output_schema JSON schema the role's response must match (validated in
                team/invocation.py; bounded retries on malformed output)

The output envelope is shared (summary, findings with cited evidence,
recommendation, confidence); each role extends it with its own fields.
"""
from __future__ import annotations

FINDINGS_ITEM = {
    "type": "object",
    "required": ["point", "evidence"],
    "properties": {
        "point": {"type": "string"},
        "evidence": {"type": "string"},
    },
}


def make_role(name: str, title: str, mandate: str, input_spec: str, output_schema: dict) -> dict:
    return {
        "name": name,
        "title": title,
        "mandate": mandate,
        "input_spec": input_spec,
        "output_schema": output_schema,
    }


def base_schema(role_name: str, extra_props: dict | None = None, extra_required: list[str] | None = None) -> dict:
    """Common structured-output envelope. `extra_props` are optional by
    default; list field names in `extra_required` to make them mandatory."""
    props = {
        "role": {"const": role_name},
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": FINDINGS_ITEM},
        "recommendation": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }
    required = ["role", "summary", "findings", "recommendation", "confidence"]
    if extra_props:
        props.update(extra_props)
    if extra_required:
        required = required + extra_required
    return {"type": "object", "required": required, "properties": props}
