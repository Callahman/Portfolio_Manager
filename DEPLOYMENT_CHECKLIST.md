# Portfolio Manager — Deployment Checklist

Checklist for developing and deploying the Portfolio Manager, derived from
`PROJECT_OUTLINE.md` (§3 "Steps to Develop the Project").

**Mapping convention**

- Each **Step** in the outline (Step 0–13) is one **Epic**.
- Each epic is broken into **Stories** (a deliverable slice of the step).
- Each story contains **Tasks** — the checkbox items below.
- Each epic ends with its **Definition of Done** (the outline's "Done when"),
  as the final checklist item for that epic.
- Checkbox states: `- [ ]` not started, `- [x]` done.

**Epic index**

| Epic | Name | Outline step |
|---|---|---|
| 0 | Scaffolding | Step 0 |
| 1 | Collection (`collect/`) | Step 1 |
| 2 | Validation (`validate/`) | Step 2 |
| 3 | Analysis (`analyze/`) | Step 3 |
| 4 | Read-only LAN API (`api/`) | Step 4 |
| 5 | Team runtime on the 4090 (`team/`) | Step 5 |
| 6 | Simulated portfolio (`portfolio/`) | Step 6 |
| 7 | Pipeline wiring + delivery (1080) | Step 7 |
| 8 | Code sync: auto-pull on the 1080 | Step 8 |
| 9 | Role-scoped self-modification loop | Step 9 |
| 10 | Ad-hoc team sessions | Step 10 |
| 11 | Hardening & docs | Step 11 |
| 12 | Evaluation loop (run the weeks) | Step 12 |
| 13 | Phase B/C (real portfolio, deferred) | Step 13 |

Note: Epics 1–3 are the segregated data packages and can partially overlap
once the Epic 0 scaffolding exists.

---

## Epic 0 — Scaffolding

### Story 0.1 — Repository & private remote

- [x] Create the repo (`git init`) and connect the private remote
- [x] Add `.gitignore` (`.env`, `.venv/`, `warehouse/`, `history/`, `archives/`, generated state)
- [x] Add `.env.example` with all variables from Appendix B (watchlist, FRED series, news feeds, API/dashboard bind, WOL config, portfolio settings, session/pod limits, history window, auto-pull, smoke test, self-mod escalation, remote URL, SMTP, archive cap)
- [ ] Verify push/pull round trip: push from the 4090, pull on the 1080

### Story 0.2 — Segregated package layout

- [x] Create the top-level layout: `collect/`, `validate/`, `analyze/`, `portfolio/`, `delivery/`, `api/`, `team/`, `history/`, `archives/`, `reports/`, `systemd/`, `workflows/`
- [x] Make each of `collect/`, `validate/`, `analyze/` an independent Python package with its own storage schema (`warehouse/raw`, `warehouse/validated`, `warehouse/analytics`)

### Story 0.3 — Python environment

- [x] Create the Python venv
- [x] Pin `requirements.txt` (requests/httpx, pandas, pyarrow, fastapi/flask, python-dotenv)

### Story 0.4 — 4090 machine verification

- [x] Verify the DeepSeek harness (Qwen 3.8, already installed) runs a session against a fixture feed
- [x] Confirm the repo checkout is writable by the harness

### Story 0.5 — 1080 machine verification

- [x] Confirm no LLM of any kind is installed/running (deterministic-only by design)

### Story 0.6 — Pi (always-on) WOL verification

- [ ] Verify the Pi's scheduled WOL wakes the 1080 (with `WOL_TIMEOUT_S` verification + retry)
- [ ] Verify an on-demand WOL wakes the 1080 for ad-hoc sessions

**Definition of Done (Epic 0)**

- [ ] `git clone` on the 1080 + `pip install -r` + `.env` = working environment
- [ ] The 4090's harness can run a single role against a fixture feed over the LAN
- [ ] A push/pull round trip between the machines succeeds

---

## Epic 1 — Collection (`collect/`)

### Story 1.1 — Prices fetcher

- [x] Implement the primary free equity price source (e.g. Yahoo Finance via an unofficial client)
- [x] Implement the fallback source (e.g. stooq)
- [x] Support the configurable watchlist (holdings + candidates + SPY benchmark)
- [x] Add retry + error reporting to the fetcher

### Story 1.2 — Macro fetcher (FRED)

- [x] Implement the FRED public API fetcher for the configurable series list (rates, CPI, unemployment, etc.)
- [x] Add retry + error reporting to the fetcher

### Story 1.3 — News fetcher

- [x] Implement the RSS feed fetcher (markets, economics, sectors)
- [x] Implement the light web crawl of the small set of allowlisted free pages
- [x] Store headlines + snippets

### Story 1.4 — Raw storage

- [x] Write parquet/CSV snapshots per fetch to `warehouse/raw/` (its own schema)
- [x] Record SQLite metadata per fetch (source, fetched-at, row count, status)

### Story 1.5 — Scheduling

- [x] systemd timer: prices a few times daily (around market hours)
- [x] systemd timer: macro daily
- [x] systemd timer: news every 1–2 hours

**Definition of Done (Epic 1)**

- [ ] A week of continuous fetching with no manual intervention
- [ ] A source outage is visible and recovers automatically

---

## Epic 2 — Validation (`validate/`)

### Story 2.1 — Quality checks per source

- [x] Completeness checks per source
- [x] Staleness checks per source
- [x] Schema checks per source
- [x] Write cleaned/verified records + validation metadata to `warehouse/validated/` (its own schema)

### Story 2.2 — Data quality report

- [x] Emit a machine-readable data quality report per run (coverage, staleness, failures)

### Story 2.3 — Structured failure reports

- [x] Emit structured failure reports for any unrecovered failure (error class, stage, source, log excerpt, first/last occurrence) — the input to the self-modification loop (Epic 9)

**Definition of Done (Epic 2)**

- [x] The quality report shows coverage/staleness per source — `validate/quality.py` (per-source status ok/stale/failed, rows, latest observation, freshness; per-kind coverage)
- [ ] An induced failure (e.g. a malformed feed) produces a structured failure report and an alert

---

## Epic 3 — Analysis (`analyze/`)

### Story 3.1 — Market snapshot

- [x] Compute price moves, volume, sector performance, notable movers, macro indicator readings

### Story 3.2 — Statistical signals

- [x] Compute correlations, volatility, trend detection
- [x] Maintain signal history with forward-return stats

### Story 3.3 — Fundamentals

- [x] Compute earnings, valuations, sector rotation, ticker-specific news/events (sector rotation + ticker news/events done; earnings/valuations deferred as documented data gaps — see `analyze/fundamentals.py`)

### Story 3.4 — Macro readings

- [x] Compute FRED series values, upcoming releases, policy news

### Story 3.5 — Risk metrics

- [x] Compute portfolio risk, position/sector exposure, tail stats, proposed-limit checks

### Story 3.6 — Per-role feed assembly (`feeds.py`)

- [x] Assemble each role's bounded feed from the analytics (the `/feeds/{role}` payloads)
- [x] Enforce the per-role data tier (raw / derived / briefs) so a role can never be handed data outside its tier

### Story 3.7 — Analytics storage

- [x] Write all five analytics to `warehouse/analytics/` (its own schema)

**Definition of Done (Epic 3)**

- [ ] A daily run produces all five analytics + per-role feeds with correct, stable schemas
- [ ] Verified against hand calculations for a few days

---

## Epic 4 — Read-only LAN API (`api/`)

### Story 4.1 — Read endpoints

- [x] `GET /feeds/{role}` — per-role feeds (market snapshot, statistical signals, fundamentals, macro readings, risk metrics, derived briefs)
- [x] `GET /quality` — data quality report
- [x] `GET /failures` — structured failure reports
- [x] `GET /history` — conversation history (rolling window)

### Story 4.2 — Write endpoint

- [x] `POST /recommendation` — the only write endpoint: accepts a team recommendation, applies it to the paper portfolio, triggers delivery

### Story 4.3 — Service hardening

- [x] systemd service for the API (`systemd/pm-api.service`)
- [x] Health endpoint
- [x] Request logging

**Definition of Done (Epic 4)**

- [ ] All endpoints respond correctly from the 4090 over the LAN
- [ ] A posted recommendation is applied to the paper portfolio and delivered

---

## Epic 5 — Team runtime on the 4090 (`team/`)

### Story 5.1 — Role definitions

- [x] One file per role with mandate, input spec, and output schema for all 11 roles (Team Lead, Data Engineer, Data Analyst, Data Scientist, Financial Analyst, Economist, Risk Manager, Challenger, Portfolio Manager, MLE, Quant) — `team/roles/`
- [x] Enforce structured outputs (JSON) via the session runtime: schema validation + bounded retries on malformed output — `team/invocation.py`

### Story 5.2 — Single-role invocation

- [x] Implement single-role invocation: given a feed from the 1080, produce the role's structured output — `team/invocation.py` (`python -m team.invocation <role>`, offline iteration via `--feed-file`)
- [ ] Test each role in isolation with real 1080 feeds

### Story 5.3 — Pod manager

- [x] Form pods (small groups of 2–3 roles, `POD_MAX_ROLES` / `POD_MAX_PODS`) — `team/pods.py` (Team Lead formation with deterministic chunking fallback)
- [x] Run each pod as a separate conversation (its own transcript/context — no cross-pod spillover) — `team/pods.py` `run_pod`
- [x] Team Lead relays each pod's decision into the next pod — `team/session.py` (deterministic relay of prior pod decisions)
- [x] Round caps + Team Lead "close deliberation" mechanism — `team/session.py` (`DELIBERATION_MAX_ROUNDS` cap + per-round convergence check that may close early)

### Story 5.4 — Context discipline

- [x] Per-role bounded feeds (pre-computed on the 1080) instead of raw dumps — `analyze/feeds.py`
- [x] Summarization between deliberation rounds — `team/context.py` `summarize_round` (extractive, no extra model call)
- [x] Context assembly: agenda + recent rounds + only the digests relevant to the speaker; deterministic truncation at the budget — `team/context.py` `assemble_context`

### Story 5.5 — Alternate personality types (optional)

- [ ] Spin up alternate personalities during execution (Bull/Bear Analyst, Risk-Averse/Aggressive PM, Dovish/Hawkish Economist) as structured votes; base role's output is the synthesis

**Definition of Done (Epic 5)**

- [ ] A hand-triggered 3-round deliberation on real 1080 feeds completes with valid structured outputs
- [ ] Stays within model context
- [ ] Produces a coherent transcript

---

## Epic 6 — Simulated portfolio (`portfolio/`)

### Story 6.1 — SQLite schema

- [x] Positions table (ticker, shares, avg cost)
- [x] Cash balance
- [x] Trade log
- [x] Daily mark-to-market values

### Story 6.2 — Seed

- [x] Seed from `.env`: starting balance in the $5k–$10k regime (`PORTFOLIO_START_BALANCE`, default $10,000)
- [x] Optional starting positions (`PORTFOLIO_START_POSITIONS`)

### Story 6.3 — Paper execution

- [x] Apply a recommendation (list of actions + sizing) at close prices
- [x] Apply the assumed transaction cost (`TX_COST_BPS`) so churn is visible in the P&L
- [x] Fractional-share handling
- [x] Record each decision with the recommendation's rationale

### Story 6.4 — Daily marks + evaluation metrics

- [x] systemd timer for the daily mark-to-market job (`systemd/pm-portfolio-mark.service` + `.timer`, `python -m portfolio.metrics mark`)
- [x] Compute metrics vs the SPY benchmark: cumulative return, max drawdown, Sharpe ratio, trade count/turnover

**Definition of Done (Epic 6)**

- [ ] A recommendation can be applied
- [ ] The portfolio marks itself daily
- [ ] The metrics (return, drawdown, Sharpe, vs SPY) are computed correctly (verified against hand calculations for a few days)

---

## Epic 7 — Pipeline wiring + delivery (1080)

### Story 7.1 — Autonomous pipeline wiring

- [x] Wire the pipeline: collect → validate → analyze → portfolio → deliver → archive — `workflows/pipeline.py` + `systemd/pm-pipeline.service`/`.timer` (21:45 UTC; a failed stage halts the run, records the failure, and emails it)
- [x] Stage tracking with resumability (a failed run restarts from the last completed stage) — `workflows/pipeline.py` (`_resume_stages`: a same-day re-run after a halt skips already-completed stages)

### Story 7.2 — Report generation

- [x] Generate the markdown report to `reports/`: data quality summary, each role's analysis, deliberation highlights, final recommendation, paper-portfolio impact

### Story 7.3 — Email delivery

- [x] SMTP email on completed runs
- [x] SMTP email on run failures

### Story 7.4 — Web dashboard

- [x] Pipeline status view (last run, stages, next scheduled run)
- [x] 4090 reachability view (informational only) — dashboard `/api/monitoring` (`team_runtime_4090`, via `TEAM_RUNTIME_HEALTH_URL` → `team/health.py` on the 4090)
- [x] Data freshness per source
- [x] Team conversation/ideation transcript view (ad-hoc sessions)
- [x] Conversation-history audit view (per-session history, rolling window, decision journal) — dashboard `/api/history` + `/api/decisions` (rendered as the "Conversation history" and "Decision journal" cards)
- [x] Latest recommendation + its history
- [x] Paper-portfolio P&L, positions, trades, benchmark comparison
- [x] Failure alerts
- [x] Confirm there is **no ad-hoc trigger** (sessions start on the 4090 harness)

### Story 7.5 — Conversation history

- [x] Per-session JSONL + markdown in `history/` — `common/history.py` (`history/sessions/{id}.jsonl` + `.md`)
- [x] Rolling window (`HISTORY_WINDOW_SESSIONS`, `HISTORY_CAP_MB`); older sessions move to size-capped `archives/` (or pruned, configurable) — `common/history.py` `prune()` (prune path; runs on session end + `workflows/maintenance.py`)
- [x] Decision journal: each recommendation linked to the pod transcripts that produced it, the feeds those pods consumed (snapshot-stamped), and the subsequent outcome (paper P&L impact) — `common/history.py` `record_decision` (session_id links the transcript; `feeds_as_of` snapshot stamps; `portfolio_baseline` P&L state at decision time via the 1080's new read-only `GET /metrics`, `api/routes/metrics.py`)

**Definition of Done (Epic 7)**

- [ ] An unattended day of operation produces fresh feeds, a quality report, and dashboard updates
- [ ] A posted recommendation is applied, reported, emailed, and archived with its transcript in history

---

## Epic 8 — Code sync: auto-pull on the 1080

### Story 8.1 — Auto-pull timer

- [x] systemd timer (`AUTOPULL_INTERVAL_MIN`): `git pull` → smoke test → service restart — `systemd/pm-autopull.service`/`.timer` (15 min) + `workflows/autopull.py` (pull → smoke → restart `pm-api` via `SERVICES_TO_RESTART`; post-restart API health check with revert)

### Story 8.2 — Smoke-test gate

- [x] Known-good fixture run must pass before new code is kept (budget: `SMOKE_TEST_TIMEOUT_S`) — `workflows/smoketest.py` (imports every package + builds both FastAPI apps), invoked by `workflows/autopull.py` with a 300 s budget

### Story 8.3 — Auto-revert

- [x] Smoke-test failure → revert to the last known-good commit — `workflows/autopull.py` (`git reset --hard <old HEAD>`)
- [x] Post-restart health failure → revert to the last known-good commit — `workflows/autopull.py` (`_api_healthy`: checks the API `/health` after restart; on failure reverts to the last known-good and restarts)
- [x] Alert on any revert — `workflows/autopull.py` (`_alert`: emails on smoke-failure revert and post-restart-health-failure revert)

### Story 8.4 — Last-known-good tracking

- [x] Track the last known-good commit (tagged) — `workflows/autopull.py` (`_tag_last_known_good`: moves a `last-known-good` git tag on every verified commit and on every revert)

**Definition of Done (Epic 8)**

- [ ] A push from the 4090 is applied on the 1080 within one timer interval
- [ ] A deliberately broken push is auto-reverted with an alert
- [ ] The pipeline keeps serving after the revert

---

## Epic 9 — Role-scoped self-modification loop (failures + feature requests)

### Story 9.1 — Failure self-heal path

- [x] Route `/failures` reports to the matching role session on the 4090 (per its edit scope, §2.2) — `team/self_mod.py` (fetches open failures from the 1080 API, groups by source → owning role)
- [x] Diagnosis: role reads the report + related code — `team/self_mod.py` (failure reports + the in-scope files' current code are passed to the role)
- [x] Fix within the role's own scope only (DE: `collect/` + `validate/`; DS: `validate/` + `analyze/`; Analyst: `analyze/`; MLE: `analyze/` + workflow code) — `team/self_mod.py` (scope enforced by construction: prices/macro/news → Data Engineer → `collect/` only; out-of-scope or nonexistent paths are rejected)
- [x] Tagged commit (`self-mod: <failure-id>`) + push to the private remote — `team/self_mod.py` (marked commit `self-mod (<role>): <summary>` + push; smoke-gated, reverted on smoke failure)
- [x] 1080 auto-pull + smoke test → verify (next run: does the failure persist?) or auto-revert — `workflows/autopull.py`

### Story 9.2 — Feature request path

- [ ] Record feature requests from pods in the pod transcript + change log (what, why, target package, proposed approach)
- [ ] The role with the matching edit scope implements it in its own scope (e.g. Quant asks for a model → MLE or Data Scientist updates `analyze/`)
- [ ] Tagged commit (`self-mod: <feature-id>`) + push
- [ ] Verify the new capability works as requested, or auto-revert

### Story 9.3 — Guardrails

- [x] Enforce per-role bounded scope — self-modification never touches `portfolio/`, `delivery/`, `api/`, `team/` — `team/self_mod.py` (fixes are limited to `collect/`; the commit only stages `collect`/`validate`/`analyze`)
- [ ] Change log in `reports/`: failure/feature id, diagnosis, files changed, outcome
- [x] Escalation: repeated fixes for the same failure class (N consecutive, `SELF_MOD_MAX_ESCALATIONS`) pause the loop for that class and escalate to the user with the diagnosis — `team/self_mod.py` (escalation counter in `history/self_mod/escalations.json`; at the limit the loop stops and emails; a successful fix resets it)

**Definition of Done (Epic 9)**

- [ ] An induced fetcher bug (e.g. a changed feed format) is diagnosed and fixed end-to-end by the loop, with a tagged commit, a change-log entry, and a verified 1080 run
- [ ] A second induced regression is caught by the smoke-test gate and auto-reverted
- [ ] A feature request (e.g. a new model) is implemented end-to-end by the matching role, verified, and appears in the 1080's feeds

---

## Epic 10 — Ad-hoc team sessions

### Story 10.1 — Session trigger flow

- [x] User-triggered from the DeepSeek harness (goal/prompt, e.g. "analyze the semiconductor sector") — `team/session.py` (`--goal` overrides the fixed agenda with a free-form goal/prompt; documented in `SETUP.md`)
- [x] Role selection (auto or manual — an ad-hoc run may need only a subset of roles) — `team/session.py` (`--roles r1,r2,...` manual, or the Team Lead forms pods from all available roles)
- [ ] WOL wakes the 1080 (if not already awake) so it can serve feeds

### Story 10.2 — Fetch, deliberate, return

- [x] Each role fetches its role-appropriate feed (GET /feeds/{role}); Data Engineer also fetches /quality and /failures — `team/invocation.py` `fetch_feed` (the Data Engineer's feed carries the quality brief + open failure reports + source status, `analyze/feeds.py`)
- [x] Roles deliberate in pods against current data — `team/session.py` (bounded rounds of pod deliberation on the live feeds)
- [x] Final recommendation returned to the 1080 (POST /recommendation) → applied, delivered, archived — `team/session.py` `--post` (posts to `POST /recommendation` and records the decision journal entry)

### Story 10.3 — Recording

- [x] Ad-hoc sessions recorded in conversation history exactly like any other session (per-pod JSONL + markdown) — `team/session.py` (every session writes the transcript via `common/history.py`)

**Definition of Done (Epic 10)**

- [ ] An ad-hoc question produces a delivered answer using current 1080 data
- [ ] The autonomous pipeline is not disturbed by the session

---

## Epic 11 — Hardening & docs

### Story 11.1 — External dependency hardening

- [x] Retries, timeouts, and degradation paths for every external dependency (sources, SMTP, dashboard, API) — visible failure state, never silent

### Story 11.2 — Storage maintenance

- [x] Archive size caps (oldest deleted first, `ARCHIVE_CAP_GB`) — `workflows/maintenance.py` (daily via `systemd/pm-maintenance.timer`)
- [x] Log rotation — `workflows/maintenance.py` (pipeline logs rotated over 5 MB, keep 3)

### Story 11.3 — Monitoring

- [x] Simple health view: fetch freshness, last run, disk usage, 4090 reachability — dashboard `/api/monitoring` (API self-status, 4090 team-runtime reachability, pipeline state, quality-report age, disk usage via `shutil.disk_usage`) + `/api/freshness` + `/api/status`

### Story 11.4 — Documentation

- [x] Write `README.md` (purpose + quick start)
- [x] Write `SETUP.md` (deployment guide, mirroring the `LLM_Server` style), including the update flow (4090 push → 1080 auto-pull → smoke test)

**Definition of Done (Epic 11)**

- [ ] A fresh-machine deployment from the docs succeeds
- [ ] A week of unattended operation with no manual fixes

---

## Epic 12 — Evaluation loop (run the weeks)

### Story 12.1 — Run the weeks

- [ ] Run sessions over several weeks
- [ ] Review paper-portfolio performance vs SPY and the per-decision record (decision journal)

### Story 12.2 — Role/prompt tuning

- [ ] Tune roles/prompts based on observed failures (hallucinated numbers, shallow analysis, overtrading, non-convergence)
- [ ] Use the conversation history as the evidence base for each change

### Story 12.3 — Evaluation documentation

- [ ] Document what the team got right/wrong
- [ ] Assess Phase B readiness (gated on decision-quality review, not a P&L target)

**Definition of Done (Epic 12)**

- [ ] A written evaluation of the first N weeks exists
- [ ] Concrete prompt/pipeline changes applied and re-verified

---

## Epic 13 — Phase B/C (real portfolio, deferred)

### Story 13.1 — Phase B: read-only real holdings

- [ ] Shortlist and pick the brokerage connection: Alpaca API / IBKR API / CSV import of brokerage statements
- [ ] Implement a read-only holdings fetcher (positions, cash, cost basis) in `collect/`, with the same quality checks as other sources
- [ ] Add a "real portfolio" view to the dashboard (holdings + latest recommendation mapped onto them); keep the paper portfolio running in parallel for comparison
- [ ] Gate: run 2–4 weeks; verify recommendations are sensible against real positions before considering execution

### Story 13.2 — Phase C: automated execution with human-in-the-loop

- [ ] Implement the order-proposal flow: recommendation → normalized orders (ticker, side, quantity, limit) → pending-approval state
- [ ] Approval UI: dashboard approve/reject (+ email with a reply mechanism as fallback)
- [ ] Execute via the chosen brokerage API in **paper mode** (e.g. Alpaca paper trading) until the approval/execution path is proven
- [ ] Add guardrails before any live trading: max order size, allowed-ticker list, daily/weekly trade caps, global kill switch
- [ ] Consider live orders only then — and keep the human approval step

**Definition of Done (Epic 13)**

- [ ] Phase B: recommendations run credibly against real holdings for the gate period (no execution)
- [ ] Phase C: a proposed order set is approved by the user and executed in paper mode end-to-end, with all guardrails active

---

## Cross-cutting concerns to keep in view (from §4)

These are not separate epics, but risks that should be checked against while
working through the relevant epics:

- [ ] **Hallucinated data** (Epic 5): roles receive only 1080 feeds; outputs require references to data keys/fields; a validation pass checks numeric claims against the warehouse — the prompt rules require every finding to cite a feed field path (`team/invocation.py`), but the numeric-claims validation pass against the warehouse is not implemented
- [x] **Context-window limits** (Epic 5): bounded feeds, round caps, deterministic truncation — `analyze/feeds.py` (bounded per-role feeds), `DELIBERATION_MAX_ROUNDS` cap, `team/context.py` (deterministic truncation at the budget)
- [x] **Free data-source fragility** (Epic 1): fallback source per data type, caching, staleness thresholds, visible failures (fallback implemented for prices; caching/staleness/visible failures for all sources)
- [x] **Deliberation non-convergence** (Epic 5): hard round budget, Team Lead close authority, deadlock detection, final recommendation always produced — `team/session.py` (hard round budget, convergence-based close, deadlock detection on identical consecutive round summaries, and a conservative hold fallback if both the Portfolio Manager and Team Lead synthesis fail)
- [x] **Overtrading** (Epic 6): transaction costs on every trade, turnover limits in the PM mandate, Risk Manager turnover checks, trade count/turnover as a first-class metric — `portfolio/` (transaction costs `TX_COST_BPS` + trade count/turnover metrics) and explicit turnover limits in the PM mandate (`~25%` of portfolio value per session, no double-trading) and Risk Manager mandate (flag session turnover above threshold)
- [ ] **Dashboard/API/email exposure** (Epic 4, 7): LAN-only bind, non-guessable port/path; shared-token auth planned early (see §5.7) — LAN-only bind is implemented (default `0.0.0.0` on the 1080 LAN); ports are conventional (8300/8400) and shared-token auth is not yet implemented
- [x] **Self-modification risk** (Epic 8, 9): per-role bounded scope, smoke-test gate, auto-revert, tagged commits + change log, escalation — `team/self_mod.py` (per-role bounded scope, smoke-test gate, auto-revert, marked commits, escalation, and a change log in `reports/self_mod_changelog.md`) + `workflows/autopull.py` (smoke-test gate + auto-revert)
- [ ] **WOL reliability** (Epic 0, 10): Pi verifies each wake (timeout + retry); missed wakes surfaced as alerts; dashboard shows 1080 data freshness — WOL lives on the Pi (outside this repo); the dashboard does surface 1080 data freshness (`/api/freshness`)
