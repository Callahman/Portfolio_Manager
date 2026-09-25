"""Context discipline (Epic 5, Story 5.4) — bounded, deterministic context
assembly for multi-round deliberation.

The main defense against context-window limits (outline §4.3): every prompt
after round 1 is assembled from (agenda + inter-round summaries +
speaker-relevant digests), with deterministic truncation at a character
budget. Inter-round summarization is extractive and free: every role output
carries a `summary` field, so a round's summary is the concatenation of its
speakers' summaries — no extra model call.
"""
from __future__ import annotations

import json

DEFAULT_BUDGET_CHARS = 12000


def summarize_round(entries: list[dict]) -> str:
    """Extractive summary of a round: each speaker's own `summary` field."""
    parts = []
    for e in entries:
        role = e.get("role", "?")
        content = e.get("content")
        if isinstance(content, dict):
            s = content.get("summary")
            if s:
                parts.append(f"{role}: {s}")
        elif isinstance(content, str) and content:
            parts.append(f"{role}: {content[:400]}")
    return " | ".join(parts) if parts else "(no entries)"


def _render(agenda: str, summaries: list[str], digests: dict | None) -> str:
    sections = [f"AGENDA:\n{agenda}"]
    if summaries:
        sections.append(
            "PREVIOUS ROUNDS (summaries, oldest first):\n"
            + "\n".join(f"- {s}" for s in summaries)
        )
    if digests:
        sections.append("RELEVANT DIGESTS:\n" + json.dumps(digests, indent=2))
    return "\n\n".join(sections)


def assemble_context(
    *,
    agenda: str,
    round_summaries: list[str] | tuple[str, ...] = (),
    digests: dict | None = None,
    budget: int = DEFAULT_BUDGET_CHARS,
) -> str:
    """Assemble the bounded context. Truncation is deterministic: drop the
    oldest round summaries first, then clip — never the agenda."""
    summaries = list(round_summaries)
    text = _render(agenda, summaries, digests)
    while len(text) > budget and summaries:
        summaries.pop(0)
        text = _render(agenda, summaries, digests)
    if len(text) > budget:
        text = text[: budget - 80] + "\n... [truncated at context budget] ..."
    return text
