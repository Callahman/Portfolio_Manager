"""Single-role invocation (Epic 5, Story 5.2).

Pipeline:
  1. fetch the role's bounded feed from the 1080 (GET /feeds/{role})
  2. assemble the prompt (mandate + output schema + feed, plus optional
     phase instructions from the session runtime)
  3. call the local model (koboldcpp at KOBOLDCPP_URL) — JSON mode
     (json_schema) when the server supports it, plain generation otherwise
  4. parse + validate the response against the role's schema (or an
     override schema, e.g. the self-mod fix schema)
  5. bounded retries on malformed output

CLI:
  python -m team.invocation <role> [--api-base URL] [--feed-file FILE]
                            [--max-retries N]

`--feed-file` lets you iterate offline against a saved feed (capture one
from the 1080 with: curl http://<1080>:8400/feeds/<role> -o feed.json).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import jsonschema
import requests

from common import config
from team.roles import get_role

log = logging.getLogger(__name__)

DEFAULT_KOBOLDCPP_URL = "http://localhost:5001"
GENERATE_TIMEOUT_S = 300
TEMPERATURE = 0.4
DEFAULT_MAX_LENGTH = 1024


class InvocationError(RuntimeError):
    """A role produced no valid structured output after all retries."""


# ------------------------------------------------------------------- feed ---

def fetch_feed(role: str, api_base: str | None = None, timeout: float = 30.0) -> dict:
    """GET /feeds/{role} from the 1080 read-only API."""
    base = (api_base or config.get("FEED_API_BASE") or "").rstrip("/")
    if not base:
        raise ValueError("no 1080 API base — set FEED_API_BASE in .env or pass --api-base")
    r = requests.get(f"{base}/feeds/{role}", timeout=timeout)
    r.raise_for_status()
    return r.json()


# ----------------------------------------------------------------- prompt ---

def build_prompt(
    role_def: dict,
    feed: dict,
    extra_instructions: str | None = None,
    schema: dict | None = None,
) -> str:
    effective = schema or role_def["output_schema"]
    schema_json = json.dumps(effective, indent=2)
    feed_json = json.dumps(feed, indent=2)
    phase = f"\nPHASE CONTEXT:\n{extra_instructions}\n" if extra_instructions else ""
    return (
        f"You are the {role_def['title']} on the Portfolio Manager team.\n\n"
        f"MANDATE:\n{role_def['mandate']}\n\n"
        f"YOUR FEED CONTAINS:\n{role_def['input_spec']}\n\n"
        f"RULES:\n"
        f"- Work only from the FEED below (and the PHASE CONTEXT). "
        f"Do not invent numbers, facts, or events.\n"
        f"- Every finding must cite its evidence as a feed field path "
        f"(e.g. assets[0].change_1d_pct).\n"
        f"- If the feed is missing, stale, or has gaps, say so — do not paper over it.\n"
        f"- Respond with ONLY one JSON object matching the schema. "
        f"No prose, no markdown fences.\n"
        f"{phase}\n"
        f"SCHEMA:\n{schema_json}\n\n"
        f"FEED:\n{feed_json}\n\n"
        f"JSON:\n"
    )


# ------------------------------------------------------------- generation ---

def _result_text(result) -> str:
    """Normalize a koboldcpp result to the completion string. Builds differ:
    most return a plain string, some wrap it in an object (e.g. {"text": ...})."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("text", "completion", "output", "result"):
            val = result.get(key)
            if isinstance(val, str):
                return val
        log.warning("unexpected koboldcpp result object — using str(): %s", result)
        return str(result)
    return str(result)


def generate(prompt: str, schema: dict | None, max_length: int = DEFAULT_MAX_LENGTH) -> str:
    """One completion from koboldcpp. Tries JSON mode (json_schema) first when
    a schema is given; falls back to plain generation if the server rejects
    the parameter (older builds). A dead server is a hard error, not a
    fallback."""
    base = (config.get("KOBOLDCPP_URL", DEFAULT_KOBOLDCPP_URL) or DEFAULT_KOBOLDCPP_URL).rstrip("/")
    url = f"{base}/api/v1/generate"
    attempts: list[dict] = []
    if schema is not None:
        attempts.append({"json_schema": json.dumps(schema)})
    attempts.append({})
    last: Exception | None = None
    for extra in attempts:
        body = {"prompt": prompt, "max_length": max_length, "temperature": TEMPERATURE, **extra}
        try:
            r = requests.post(url, json=body, timeout=GENERATE_TIMEOUT_S)
            r.raise_for_status()
            results = r.json().get("results") or []
            if not results:
                raise ValueError("koboldcpp returned empty results")
            return _result_text(results[0])
        except requests.HTTPError as e:
            last = e
            if extra and e.response is not None and e.response.status_code == 400:
                log.warning("server rejected json_schema (400) — falling back to plain generation")
                continue
            raise
    assert last is not None
    raise last


# --------------------------------------------------------------- validation ---

def parse_json(text: str) -> dict:
    """Extract the first balanced JSON object from a completion (the model
    may emit stray prose despite the instructions)."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in completion")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("unbalanced JSON in completion")


def validate(payload: dict, schema: dict) -> None:
    jsonschema.validate(instance=payload, schema=schema)


# ----------------------------------------------------------------- invoke ---

def invoke_role(
    role: str,
    api_base: str | None = None,
    feed: dict | None = None,
    max_retries: int = 3,
    extra_instructions: str | None = None,
    output_schema: dict | None = None,
) -> dict:
    """Fetch the feed, run the role, and return its validated structured output.

    `extra_instructions` carries the session phase (formation, relay, fix,
    ...). `output_schema` overrides the role's schema for phase-specific
    outputs (e.g. the self-mod fix schema).

    Returns {role, output, attempts, raw}. Raises InvocationError after all
    retries fail; ValueError / RequestException on feed or API problems.
    """
    role_def = get_role(role)
    if feed is None:
        feed = fetch_feed(role, api_base)
    prompt = build_prompt(role_def, feed, extra_instructions=extra_instructions, schema=output_schema)
    schema = output_schema or role_def["output_schema"]
    last_err = ""
    for i in range(1, max_retries + 1):
        raw = generate(prompt, schema)
        try:
            payload = parse_json(raw)
            validate(payload, schema)
            return {"role": role, "output": payload, "attempts": i, "raw": raw}
        except (json.JSONDecodeError, jsonschema.ValidationError, ValueError) as e:
            last_err = str(e)
            log.warning("attempt %d/%d for %s failed: %s", i, max_retries, role, last_err)
    raise InvocationError(
        f"{role}: no valid structured output after {max_retries} attempts — {last_err}"
    )


# --------------------------------------------------------------------- cli ---

def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not argv:
        print(__doc__)
        return 1
    role = argv[0]
    api_base: str | None = None
    feed_file: str | None = None
    max_retries = 3
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--api-base":
            api_base = argv[i + 1]
            i += 2
        elif a == "--feed-file":
            feed_file = argv[i + 1]
            i += 2
        elif a == "--max-retries":
            max_retries = int(argv[i + 1])
            i += 2
        else:
            log.error("unknown argument: %s", a)
            return 1
    config.load_env()
    feed = None
    if feed_file:
        feed = json.loads(Path(feed_file).read_text(encoding="utf-8"))
    try:
        res = invoke_role(role, api_base=api_base, feed=feed, max_retries=max_retries)
    except (InvocationError, ValueError, requests.RequestException) as e:
        log.error("%s", e)
        return 1
    print(json.dumps(res["output"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
