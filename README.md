# Portfolio Manager

A paper-trading portfolio system: free market data (prices, macro, news) is
collected on the 1080, validated, analyzed, and served to a bounded
"team" of LLM roles on the 4090 that deliberate in pods and produce a
daily recommendation. The 1080 paper-executes it, marks the portfolio,
reports, and monitors. The 1080 auto-pulls the 4090's code changes and a
role-scoped self-modification loop fixes ingestion failures.

## Machines

| Machine | Role | Runs |
|---|---|---|
| **1080** (Linux, systemd) | Data + execution + monitoring | collectors, validate/analyze, portfolio, API, dashboard, pipeline, autopull, maintenance |
| **4090** (Windows) | Team runtime | koboldcpp (local model), role invocation, pod sessions, self-mod loop, health endpoint |
| **Pi** (optional) | Wake-on-LAN for the 4090 | WOL only |

## Layout

```
common/       config, paths, failure reports, conversation history
collect/      prices (stooq/finviz), macro (FRED), news (RSS) -> warehouse/raw
validate/     quality checks -> warehouse/validated + quality report
analyze/      signals, fundamentals, macro, risk -> warehouse/analytics + role feeds
portfolio/    paper execution, marks, metrics
delivery/     reports, email, failure dispatch, dashboard (FastAPI)
api/          read-only LAN API (feeds, quality, failures, POST /recommendation)
team/         role definitions, invocation, pods, context, sessions, self-mod, health
workflows/    pipeline, autopull, smoke test, maintenance
systemd/      all 1080 units + timers
```

## Data flow

```
1080:  collect -> validate -> analyze -> (feeds via API)
4090:  team session (pods x rounds) -> final recommendation -> POST /recommendation
1080:  paper execute -> mark -> report + email -> archive
1080:  autopull (15 min) pulls 4090 commits, smoke-tests, auto-reverts on failure
4090:  self-mod (nightly) reads open failures, role-scoped fix -> push
```

## Key operations

- **Daily run (1080):** `pm-pipeline.timer` (21:45 UTC) chains
  collect → validate → analyze → mark → deliver → archive with stage
  tracking (`history/pipeline/state.json`) and failure halt + email.
  Standalone `pm-validate` / `pm-analyze` / `pm-portfolio-mark` timers also
  exist for on-demand runs.
- **Session (4090):** `python -m team.session [--roles r1,r2,...] [--rounds 3] [--post]`
  The Team Lead forms pods from available roles (or you select ad-hoc roles);
  pods deliberate in shared conversations; the Team Lead relays pod decisions,
  may close early, and synthesizes the final recommendation; the transcript
  lands in `history/sessions/` and a posted recommendation lands in the
  decision journal.
- **Single role (4090):** `python -m team.invocation <role>` — test any of
  the 11 roles in isolation against the 1080's feed.
- **Self-mod (4090):** `python -m team.self_mod [--dry-run]` — role-scoped
  fixes for open ingestion failures (data_engineer → `collect/` only),
  smoke-gated, with bounded escalations.
- **Monitoring (1080):** dashboard `:8300` — status, freshness, portfolio,
  failures, recommendation, history, **monitoring** (API + 4090 reachability
  + pipeline state), **decision journal**.

## API (1080, `:8400`)

Read-only, except:

- `GET /feeds/{role}` — bounded feed for one of the 11 roles
- `GET /quality`, `GET /failures`, `GET /history`, `GET /recommendation`
- `POST /recommendation` — `{actions: [{ticker, side, shares, rationale}], rationale}`

## Roles (11)

`team_lead` (orchestrator), `data_engineer`, `data_analyst`,
`data_scientist`, `financial_analyst`, `economist`, `risk_manager`,
`challenger`, `portfolio_manager`, `mle`, `quant`.

## Setup

See [SETUP.md](SETUP.md).
