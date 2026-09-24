# Portfolio Manager — Project Outline

An automated "team" of LLM agents that recommends an investment strategy
for a particular user's portfolio. The deterministic data engine runs on the
1080 (woken on a schedule); the team deliberates on demand on the 4090 —
typically one session per week, but user-triggered, not scheduled.

Hosted on **three machines** on the same LAN:

- **Pi (always-on, low-power, e.g. Raspberry Pi)** — the always-on anchor.
  Runs the **scheduled WOL** that wakes the 1080 to run the data engine, and
  can send an on-demand WOL to wake the 1080 for ad-hoc team sessions.
- **1080 machine (8 GB VRAM, 32 GB RAM, ample disk, internet access)** —
  **not always-on**: woken by WOL (from the Pi), then runs the
  **purely deterministic, LLM-free** data engine: collect → validate →
  analyze → paper portfolio → deliver → archive. While awake it serves the
  read-only HTTP API on the LAN, then returns to sleep.
- **4090 machine (24 GB VRAM, RTX 4090)** — on demand: the LLM team —
  **Qwen 3.8 in a DeepSeek harness** (already installed). Sessions are
  user-triggered, **fetch** data/analytics from the 1080 over the LAN
  (they do not run the pipeline), and return a recommendation. Because the
  DeepSeek harness is a coding-agent runtime, it **can modify the shared
  repo** — the sanctioned path is the role-scoped **self-modification loop** (failures + feature requests; each
  role that can edit code is limited to its own scope; smoke-test gate,
  auto-revert).

No cloud APIs, no external ToS, no per-token cost (same philosophy as
`D:\LLM\LLM_Server`). No Ollama — the 1080's old LLM methodology is
dropped; the 1080 is LLM-free by design.

> Naming note: "Qwen 3.8" and "DeepSeek harness" are used exactly as
> written. If "3.8" is shorthand for a specific model tag (a particular
> Qwen3 size/quant), the exact tag should be pinned in the harness config
> and in Appendix B.

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Overall Project Outline](#2-overall-project-outline)
3. [Steps to Develop the Project](#3-steps-to-develop-the-project)
4. [Concerns with the Initial Version](#4-concerns-with-the-initial-version)
5. [Future Improvements & Next Steps](#5-future-improvements--next-steps)

---

## 1. Purpose

The purpose of this project is to **replace the manual "read the news, check
the numbers, decide what to do" loop with an automated, repeatable process**:

- A **team of LLM "roles"** (Team Lead, Data Engineer, Data Analyst, Data
  Scientist, Financial Analyst, Economist, Risk Manager, Challenger
  (Devil's Advocate), Portfolio Manager, Machine Learning Engineer,
  Quantitative Researcher) each bring a distinct perspective to the same
  freshly fetched data. During execution, **alternate personality types**
  (e.g. Bull/Bear Analyst, Risk-Averse/Aggressive PM, Dovish/Hawkish
  Economist) can be spun up per role — see the roles table (§2.2).
- The **1080 machine — woken by WOL from the always-on Pi — fetches freely
  available data** (web crawling, public APIs) — structured (prices, macro
  indicators) and unstructured (news, commentary) — and computes all
  deterministic analysis in code.
- The **4090 machine's team analyzes, converses, and ideates** in
  **pods** — small groups of roles (2–3) that discuss a specific topic in
  their own room, so conversations don't spill over into each other. The
  **Team Lead conducts the pods**, relaying each pod's decision into the
  next (e.g. a results pod → an implementation pod → a data-needs pod) and
  driving convergence; the Challenger argues against the draft until it is
  defended.
- The team **recommends a concrete investment strategy for the user's
  portfolio for the next week** (buy / sell / hold / trim, position sizing,
  risk notes, confidence), delivered as a report file, an email, and a
  dashboard entry.
- In **v1 the strategy is applied to a simulated (paper) portfolio** with a
  realistic small-portfolio starting balance ($5k–$10k) so the team's
  decisions can be evaluated over time (vs. a benchmark like SPY) before any
  real portfolio is connected. A **phased approach** leads to a real
  portfolio with an automated connection (read-only first, then
  human-in-the-loop execution).

### Operating mode

- **Autonomous (Pi → 1080)**: the always-on **Pi runs the scheduled WOL**,
  waking the 1080. The 1080 then runs the deterministic pipeline — collect
  → validate → analyze → paper portfolio → deliver → archive — LLM-free,
  serves the API while awake, and returns to sleep. Unaffected by the 4090's
  power state. The user receives failure alerts — no action needed.
- **Ad-hoc (4090)**: the user triggers a team session **from the DeepSeek
  harness** (not the dashboard). A WOL wakes the 1080 (if not already
  awake) so it can serve feeds; the roles fetch role-appropriate feeds from
  the 1080 over the LAN, deliberate against current data, and return a
  recommendation to the 1080 (POST /recommendation), which applies it to
  the paper portfolio and delivers the report.

### Non-goals (v1)

- No real money, no live trading.
- No cloud LLM APIs.
- No LLM on the 1080 machine (8 GB VRAM — deterministic only).

## 2. Overall Project Outline

### 2.1 Architecture

```
+------------------------------------------------------------------------+
| Pi (always-on, low-power — the anchor)                                 |
|                                                                        |
|  - runs the SCHEDULED WOL -> wakes the 1080 to run the data engine     |
|  - can send an ON-DEMAND WOL -> wakes the 1080 for ad-hoc sessions     |
+------------------------------------------------------------------------+
        |  WOL (scheduled + on-demand)
        v
+------------------------------------------------------------------------+
| 1080 machine (woken by WOL, deterministic, LLM-free)                  |
|                                                                        |
|  +----------------+  while awake: systemd timers keep data fresh       |
|  | collect/       |   - prices:  free equity price sources             |
|  |  fetchers      |   - macro:   FRED (public API)                     |
|  |                |   - news:    RSS feeds / light web crawl           |
|  +-------+--------+   - state:   paper-portfolio (SQLite)              |
|          v                                                             |
|  +----------------+  warehouse/raw/ (its own schema: parquet/CSV       |
|  | warehouse      |  + SQLite metadata)                               |
|  |  raw/          +--> warehouse/validated/ (its own schema:           |
|  |  validated/      cleaned/verified records + validation metadata)    |
|  |  analytics/    +--> warehouse/analytics/ (its own schema:           |
|  +-------+--------+      snapshot, signals, fundamentals, macro        |
|          v                       readings, risk metrics — all in code) |
|  +----------------+                                                    |
|  | analyze/       |  per-role feeds (bounded digests) for the 4090    |
|  |  (deterministic|  team: market snapshot, statistical signals,       |
|  |   digests)     |  fundamentals, macro readings, risk metrics       |
|  +-------+--------+                                                    |
|          v                                                             |
|  +----------------+                                                    |
|  | portfolio/     |  paper portfolio ($5k-$10k): positions, cash,     |
|  |  (SQLite)      |  trades, daily mark-to-market, metrics vs SPY     |
|  +-------+--------+                                                    |
|          v                                                             |
|  +----------------+                                                    |
|  | delivery/      |  - report file (markdown, reports/)               |
|  |                |  - email (SMTP)                                   |
|  |                |  - web dashboard (LAN): status, freshness,        |
|  |                |    recommendation, paper P&L, transcript +        |
|  |                |    conversation-history audit view                |
|  |                |    (no ad-hoc trigger: sessions start on the      |
|  |                |    4090 harness)                                  |
|  +-------+--------+                                                    |
|          v                                                             |
|  +----------------+                                                    |
|  | archives/      |  permanent size-capped record                     |
|  +-------+--------+                                                    |
|                                                                        |
|  +----------------+                                                    |
|  | api/           |  read-only LAN HTTP API (served while awake):     |
|  |                |   GET  /feeds/{role}  /quality  /failures         |
|  |                |        /history                                     |
|  |                |   POST /recommendation (the only write)           |
|  +-------+--------+                                                    |
|                                                                        |
|  +----------------+                                                    |
|  | systemd        |  auto-pull timer: git pull -> smoke test ->       |
|  |  (services +   |  restart; auto-revert on failure — the only       |
|  |  timers)       +--> entry point for 4090 repo changes             |
|  +----------------+                                                    |
|                                                                        |
|  (returns to sleep after the run / when idle)                          |
+------------------------------------------------------------------------+
        |  LAN: feeds in, recommendation out (POST /recommendation)
        v  + private git remote: 4090 pushes, 1080 auto-pulls
+------------------------------------------------------------------------+
| 4090 machine (on demand)                                               |
|                                                                        |
|  DeepSeek harness (coding-agent runtime, already installed)            |
|  running Qwen 3.8                                                      |
|  - team session (user-triggered): all roles fetch role-appropriate     |
|    feeds from the 1080 -> deliberate -> recommend ->                   |
|    POST /recommendation                                                |
|  - role-scoped self-mod: failures + feature requests; any role with edit permissions reads         |
|    /failures and modifies the repo ONLY within its own scope           |
|    (ingestion / ETL / analysis) -> push -> 1080 auto-pull             |
|  - because it is a coding agent, it can modify the shared repo         |
|    (role-scoped + smoke-test gate + auto-revert)                       |
|  - idles the rest of the time                                          |
+------------------------------------------------------------------------+
```

### 2.2 The roles (LLM "personalities")

Each role is a system prompt with a distinct mandate, a defined input
(which feeds it consumes), and a structured output (what it must
produce). The session runtime enforces the structure; the model supplies
the substance.

| Role | Mandate | Key output | Data feed | Allowed data types | Alternate personalities (spun up during execution) | Edit permissions (self-mod scope) |
|---|---|---|---|---|---|---|
| **Team Lead** | Conducts the whole session: **forms the pods** (small groups of 2–3 roles) and **relays each pod's decision into the next pod**, sets the agenda, enforces round limits, breaks deadlocks, verifies convergence, signs off the final synthesis. Has authority to close deliberation. | Run plan, convergence verdict, final synthesis notes | Agenda/convergence state (in-session); data quality report (1080) | Briefs + quality report (no raw) | — | — |
| **Data Engineer** | Owns the fetch pipeline: sources, schedules, retries, schema, data quality. Reports gaps and staleness so the team knows what it *doesn't* know. Participates in self-modification (§2.9) within its own scope. | Data quality report (coverage, staleness, failures); self-mod fixes | /quality, /failures, per-source status (1080) | Raw + quality/failure reports | — | Ingestion (`collect/`) + ETL (`validate/`) |
| **Data Analyst** | Interprets the deterministic market snapshot: price moves, volume, sector performance, notable movers, macro indicator readings. | Market-snapshot commentary (structured) | Market snapshot (1080, derived stats) | Raw + derived | — | Analysis (`analyze/`) |
| **Data Scientist** | Statistical layer: correlations, volatility, trend detection, signal extraction; sanity-checks the team's proposed rules against the data (e.g. "this pattern has occurred N times; forward returns averaged X"). | Statistical signals + backtest-style sanity checks | Statistical signals (1080: correlations, volatility, trends, signal history) | Raw + derived | — | ETL (`validate/`) + Analysis (`analyze/`) |
| **Financial Analyst** | Fundamentals/valuation lens: earnings, valuations, sector rotation, company-specific news and events affecting holdings or candidates. | Fundamentals brief per relevant ticker | Fundamentals (1080: earnings, valuations, rotation, ticker news) | Derived + ticker news | Bull Analyst / Bear Analyst | — |
| **Economist** | Macro lens: rates, inflation, employment, central-bank policy, global events — from FRED series + news. | Macro outlook for the coming week | Macro readings (1080: FRED values, upcoming releases, policy news) | Derived + FRED values | Dovish / Hawkish economist | — |
| **Risk Manager** | Position/sector limits, drawdown guards, correlation checks, tail risk; evaluates the draft strategy against the risk policy and flags violations the PM must address before sign-off. | Risk assessment + violation list | Risk metrics (1080: portfolio risk, exposure, tail stats) + draft strategy (in-session) | Derived + briefs (draft strategy) | Conservative / Aggressive risk manager | — |
| **Challenger (Devil's Advocate)** | Argues against the draft strategy: stress-tests assumptions, presents counter-evidence, forces the PM to defend every position. A recommendation that survives the Challenger is stronger. | Counter-arguments + "what would break this plan" list | Draft strategy (in-session) + counter-evidence digest (1080) | Briefs + derived counter-evidence | Mild Skeptic / Hardline Contrarian | — |
| **Portfolio Manager** | Integrates all analyses into a concrete strategy for *this user's portfolio*: actions, sizing, rebalancing, risk limits, position changes — and defends it during deliberation. | The final recommendation (actions, sizing, risk notes, confidence) | **Derived team briefs** (in-session structured outputs of the other roles) — not raw data | **Briefs only (no raw data)** | Risk-Averse PM / Aggressive PM | — |
| **Machine Learning Engineer (MLE)** | Manages the algorithmic workflows: feature stores, model training/serving, workflow orchestration, model monitoring; ensures the team's algorithms run reliably and reproducibly. | Workflow status, model registry, reproducibility report | Algorithmic workflow state (model registry, feature store, workflow status) + statistical signals | Raw + derived (builds features/models) | — | Analysis (`analyze/`) + algorithmic workflow code |
| **Quantitative Researcher (Quant)** | Develops and backtests quantitative strategies and models — turns signals into concrete, testable trade rules (entry/exit, sizing, allocation); validates them against historical data before adoption. | Candidate strategies + backtest results | Statistical signals + market snapshot + signal history (for backtesting) | Raw + derived (historical data for backtesting) | Momentum / Mean-reversion quant | Analysis (`analyze/`) |

Notes:

- All roles run on the **4090 machine in a DeepSeek harness** (Qwen 3.8).
  Structured outputs are enforced by the session runtime (schema
  validation + bounded retries on malformed output).
- Roles are **configurable per session** (e.g. an ad-hoc "what do you
  think about X?" run may only need the analyst + data scientist +
  portfolio manager).
- **Pods**: the team deliberates in **pods** (small groups of 2–3 roles),
  each a separate conversation, so discussions don't spill over into each
  other; the **Team Lead** forms the pods and relays each pod's decision
  into the next (see §2.4, §2.10).
- **Allowed data types** (column): the data-access tier each role is
  permitted — **raw** (the fetched data), **derived** (the 1080 analytics),
  or **briefs** (the structured outputs of other roles). A manager
  (Portfolio Manager) receives briefs only (no raw data); a Data Scientist
  receives raw + derived. The feed assembly (`feeds.py`) enforces the tier
  per role, so a role can never be handed data outside its tier.
- **Alternate personality types** (column): spun up during execution as
  additional instances of a role with an opposite/variant mandate (e.g.
  Bull/Bear Analyst, Risk-Averse/Aggressive PM, Dovish/Hawkish Economist).
  The Team Lead runs them as a structured vote; the base role's output is
  the synthesis. See §5.5.
- **Edit permissions** (column): the self-modification scope. Only roles
  that can reasonably modify code have edit permissions, and each is
  limited to its own scope — **ingestion** (`collect/`), **ETL**
  (`validate/`), **analysis** (`analyze/`) — plus the MLE's algorithmic
  workflow code. Reasoning-only roles (Team Lead, Financial Analyst,
  Economist, Risk Manager, Challenger, Portfolio Manager) have no edit
  permissions. See §2.9.
- The 1080 machine is **LLM-free by design**: 8 GB VRAM cannot host a
  quality model, and the deterministic design means no stage needs one.
  There is no small-model degradation path.

### 2.3 Autonomous pipeline (1080, deterministic)

The pipeline lives entirely on the 1080, which is **woken by WOL** (from
the always-on Pi) and then runs the data engine. Every stage is code; no
stage needs an LLM, so the pipeline runs regardless of the 4090's power
state. The stages are **segregated packages with segregated storage
schemas** (collect/ → warehouse/raw/, validate/ → warehouse/validated/,
analyze/ → warehouse/analytics/).

```
 1. COLLECT    (continuous, scheduled — data is always fresh)
      prices, macro, news -> warehouse/raw/ (its own schema)
 2. VALIDATE   (deterministic quality checks)
      completeness / staleness / schema -> warehouse/validated/
      + data quality report + structured failure reports
 3. ANALYZE    (deterministic, in code)
      market snapshot, statistical signals, fundamentals, macro readings,
      risk metrics -> warehouse/analytics/ (its own schema)
      -> per-role feeds for the 4090 team
 4. PORTFOLIO  (paper portfolio)
      apply the latest recommendation at close prices; daily
      mark-to-market; metrics vs SPY
 5. DELIVER    (delivery layer)
      report file; email summary; dashboard update (status,
      recommendation, paper P&L, transcript + conversation-history
      audit view)
 6. ARCHIVE    (archives)
      full record (feeds consumed, recommendation, transcript, report)
      archived (size-capped)
```

Note: the numeric work (snapshot aggregation, correlations, volatility,
trend detection, backtest-style sanity checks, risk metrics) is computed
in code on the 1080 as part of analyze/; the 4090's roles interpret and
cross-examine the numbers rather than computing them.

Failure handling: any stage failure is retried (bounded), then a
**structured failure report** is emitted (error class, stage, source, log
excerpt, first/last occurrence) — exposed via /failures and surfaced as an
alert (email + dashboard). The report is the input to the Data Engineer
self-modification loop (§2.9). The pipeline is **resumable** — a failed run can be
restarted from the last completed stage.

### 2.4 Ad-hoc team session (4090, fetches from 1080)

- **Triggered from the DeepSeek harness** (user-initiated), not the
  dashboard: the user provides a goal/prompt (e.g. "analyze the
  semiconductor sector", "should I trim my SPY position?", "what's the
  risk in my current book?"). A **WOL wakes the 1080** (if not already
  awake) so it can serve feeds.
- The session runtime (team/) loads the role definitions for the session
  and assembles per-role context from the **1080 API**: each role fetches
  its role-appropriate feed (GET /feeds/{role}) — the Data Engineer also
  fetches /quality and /failures.
- The roles deliberate in **pods** (small groups of 2–3 roles, each in its
  own room) against *current* data. The **Team Lead conducts the pods**,
  relaying each pod's decision into the next — e.g. a **results pod**
  (Portfolio Manager + Quant + Team Lead) decides a new ML model is needed
  upstream; the **implementation pod** (Team Lead + MLE + Data Scientist)
  ideates the design; the **data-needs pod** (Data Scientist + MLE + Data
  Engineer) decides whether additional data is required. Each pod is a
  separate conversation, so one pod's discussion never spills into
  another's context. The Challenger argues against the draft; the Risk
  Manager checks it against the risk policy; the Portfolio Manager builds
  and defends the strategy; the Team Lead drives convergence and signs off.
- The final recommendation is **returned to the 1080** (POST
  /recommendation). The 1080 applies it to the paper portfolio, writes the
  report, sends the email, and archives the record.
- The **per-pod transcripts** are written to **conversation history**
  (history/, per-pod JSONL + markdown, rolling window — §2.10).
- Because the harness is a coding-agent runtime, the session can also
  **modify the shared repo** — the sanctioned path is the **role-scoped
  self-modification loop** (§2.9), triggered by both failures and feature
  requests/ideas from the pods (e.g. a pod decides a new model is needed →
  the MLE or Data Scientist implements it in `analyze/`).

### 2.5 Simulated portfolio (v1 evaluation vehicle)

- **SQLite database**: positions (ticker, shares, avg cost), cash balance,
  trade log, daily mark-to-market values.
- **Starting balance**: configurable in `.env` — a realistic small-
  portfolio regime of **$5,000–$10,000** (default $10,000). At this scale,
  per-trade costs and position granularity are proportionally more visible
  — churn and costs show up in the P&L instead of being hidden by size.
- **Automatic application**: each recommendation is paper-executed at
  close prices; a small **assumed transaction cost** is applied so churn
  is visible in the P&L. The execution engine handles fractional shares
  (round-lot constraints would be meaningless at this scale).
- **Evaluation metrics** (tracked over time, shown on the dashboard):
  cumulative return, max drawdown, Sharpe ratio, comparison vs. the **SPY
  benchmark**, trade count / turnover, and the per-decision record (what
  the team decided, why, and what actually happened).
- Purpose: after several weeks, the user can judge whether the team's
  decisions are credible before connecting a real portfolio.

### 2.6 Phased approach to a real portfolio

| Phase | What changes |
|---|---|
| **A (v1)** | Simulated portfolio only. Fully self-contained. |
| **B** | **Read-only real holdings**: an automated connection (brokerage API, e.g. Alpaca or IBKR — or a manual CSV import as an intermediate step) feeds the team the user's *actual* positions; recommendations are made against real holdings but nothing is executed. |
| **C** | **Automated execution with human-in-the-loop**: the team's recommendation becomes a proposed order set (e.g. via Alpaca paper trading first); the user approves/rejects via the dashboard or email before anything is placed; strict limits (max order size, allowed tickers, kill switch). |

Phase B/C design is intentionally deferred — v1 must prove out the data
pipeline, the agent team, and the evaluation loop first.

### 2.7 Delivery layer

- **Report file**: a markdown report (weekly or ad-hoc) written to
  `reports/`, containing: data quality summary, each role's analysis, the
  deliberation highlights, the final recommendation, and the paper-
  portfolio impact.
- **Email**: an SMTP-based summary (configurable in `.env`: server,
  sender, recipient) — sent on each completed run and on any run failure.
- **Web dashboard** (FastAPI/Flask, bound to the LAN, e.g. `0.0.0.0:8300`):
  - Pipeline status (last run, stages, next scheduled run)
  - 4090 reachability (online / off) — informational only
  - Data freshness per source
  - The team's conversation/ideation transcript (ad-hoc sessions)
  - **Conversation-history audit view** (per-session history, rolling
    window, decision journal — §2.10)
  - The latest recommendation and its history
  - Paper-portfolio P&L, positions, trades, benchmark comparison
  - Failure alerts
  - **No ad-hoc trigger** — sessions are triggered from the DeepSeek
    harness on the 4090, not from the dashboard.
  - *Accessibility note*: per the current plan it is reachable by anyone
    on the network who knows the URL. See Concerns §4.8 for the exposure
    risk and the planned light mitigation.

### 2.8 Conventions (borrowed from `LLM_Server`)

- **Git checkout** as the deployment model (repo on a private remote; each
  machine runs a checkout).
- **`.env` + `.env.example`** for all configuration (sources, portfolio
  settings, SMTP, dashboard port, API port, history window, sync interval)
  — real `.env` gitignored.
- **systemd** for services and timers (collect/validate/analyze stages,
  portfolio marks, delivery, API, auto-pull).
- **Archives** as the permanent, size-capped record; separate from the
  clearable/working state.
- **Graceful degradation**: every external dependency (source, SMTP) has a
  fallback path and a visible failure state rather than a silent one.
- **Three-machine deployment**: the **Pi** (always-on, low-power) runs the
  **scheduled WOL** that wakes the 1080 (and can send an on-demand WOL for
  ad-hoc sessions). The **1080 machine** (woken by WOL) runs all services +
  timers (including the auto-pull timer) while awake. The **4090 machine**
  runs the DeepSeek harness + a repo checkout (the team runtime and the
  self-modification loop need the repo). The Pi's WOL config and the 4090's harness
  config (model tag, etc.) live on their respective machines, not in this
  repo's `.env`.
- **Code sync**: the 4090 pushes to the private remote; the 1080
  **auto-pulls on a systemd timer** (`git pull` → smoke test → restart,
  **auto-revert on failure**). The 1080 never runs code that has not
  passed the smoke-test gate.
- **README.md + SETUP.md** once the project is deployable.

### 2.9 Self-modification loop (role-scoped: failures + feature requests)

The harness can modify the shared repo. Its sanctioned
use is a **self-modification loop** for the 1080's deterministic pipeline,
triggered by **two kinds of input**:

- **Failures** (self-heal): a 1080 stage fails → the matching role reads
  the failure report and fixes it.
- **Feature requests / ideas** (self-implement): a pod decides a new
  capability is needed (a new model, a new signal, a new data source) →
  the role with the matching edit scope implements it. E.g. the Quant asks
  for a model → the **MLE or Data Scientist** updates `analyze/` to include
  it.

In both cases, **any role with edit permissions** can participate, **each
limited to its own scope** (per the Edit permissions column, §2.2).
Self-modification is not limited to the Data Engineer — it is allowed for
every role that could reasonably modify code, scoped per role.

```
 1. TRIGGER   (a) FAILURE: 1080 stage fails -> structured failure report
              (error class, stage, source, log excerpt, first/last
              occurrence)
              (b) FEATURE: a pod decides a new capability is needed ->
              structured feature request (what, why, target package,
              proposed approach)
 2. EXPOSE    (a) GET /failures + alert (email + dashboard)
              (b) feature request recorded in the pod transcript + change
              log (reports/)
 3. DIAGNOSE  4090 role session — the role whose scope matches (a) the
              failure or (b) the feature target — reads the report/request
              + the related code
 4. FIX /     modify ONLY within the role's own scope (ingestion / ETL /
   IMPLEMENT analysis) — e.g. DE: collect/ + validate/; DS: validate/ +
              analyze/; Analyst: analyze/; MLE: analyze/ + workflow code
 5. PUSH      commit (tagged self-mod: <failure-id|feature-id>) + push to
              the private remote
 6. APPLY     1080 auto-pull: git pull -> smoke test -> restart
 7. VERIFY    (a) next run: does the failure persist?
              (b) does the new capability work as requested?
 8. REVERT    smoke-test failure, or (a) repeated failure / (b) capability
              not working -> auto-revert to the last known-good commit;
              escalate to the user
```

Guardrails:

- **Bounded scope (per role)**: each role's self-modification commits may touch
  only within its own scope (per §2.2) — and never `portfolio/`,
  `delivery/`, `api/`, `team/`. Specifically: **ingestion** (`collect/`)
  only the Data Engineer; **ETL** (`validate/`) the Data Engineer + Data
  Scientist; **analysis** (`analyze/`) the Data Analyst + Data Scientist +
  MLE; **algorithmic workflow code** the MLE.
- **Smoke-test gate**: a known-good fixture run must pass on the 1080
  before the new code is kept (budget: `SMOKE_TEST_TIMEOUT_S`).
- **Auto-revert**: on smoke-test failure, or when the same failure
  persists after a fix, the 1080 reverts to the last known-good commit
  automatically.
- **Change log**: every self-modification commit is tagged and recorded in the
  `reports/` change log (failure id, diagnosis, files changed, outcome).
- **Escalation**: repeated fixes for the same failure class (N
  consecutive) pause the loop for that class and escalate to the user
  with the diagnosis.

### 2.10 Conversation history & audit trail

Every team session (ad-hoc) is recorded in full, **per pod**, for future
auditing:

- **Per pod**: a machine-readable **JSONL** transcript (every message in
  that pod, with timestamp, pod id, session id, and token count) + a
  **markdown** rendering, both in `history/`. Pods are separate
  transcripts, so the history shows each pod's discussion in isolation —
  no cross-pod spillover in the record either.
- **Rolling window**: history keeps the last N sessions (and/or a size
  cap — `HISTORY_WINDOW_SESSIONS`, `HISTORY_CAP_MB`); older sessions move
  to the size-capped `archives/` (or are pruned, configurable).
- **Decision journal**: each recommendation (and each self-modification
  feature request) is linked to the **pod transcripts** that produced it,
  the data feeds those pods consumed (feeds are snapshot-stamped), and
  the subsequent outcome (paper P&L impact) — the audit path from "what
  the team said, in which pods" to "what happened".
- **Exposed**: via the 1080 API (`GET /history`) and the dashboard's
  conversation-history audit view (§2.7).
- **Purpose**: auditing, prompt/role tuning (§5.4), and the raw material
  for long-term team memory (§5.6).

---

## 3. Steps to Develop the Project

Phased development plan. Each step ends with something runnable and
verifiable. Steps 1–3 are the segregated data packages and can partially
overlap once scaffolding exists.

### Step 0 — Scaffolding

- Create the repo (git init, private remote), `.gitignore`, `.env.example`.
- Segregated layout: `collect/`, `validate/`, `analyze/`, `portfolio/`,
  `delivery/`, `api/`, `team/`, `history/`, `archives/`, `reports/`,
  `systemd/` — each of collect/validate/analyze is an independent package
  with its own storage schema (warehouse/raw, warehouse/validated,
  warehouse/analytics).
- Python venv; pin `requirements.txt` (requests/httpx, pandas, pyarrow,
  fastapi/flask, python-dotenv).
- **4090 machine**: the DeepSeek harness is already installed (Qwen 3.8) —
  verify the harness runs a session against a fixture feed; confirm the
  repo checkout is writable by the harness.
- **1080 machine**: no LLM of any kind (deterministic only).
- **Pi (always-on)**: verify the Pi's scheduled WOL wakes the 1080, and
  that an on-demand WOL works for ad-hoc sessions.
- Verify the private remote works: push from the 4090, pull on the 1080.

**Done when**: `git clone` on the 1080 + `pip install -r` + `.env` =
working environment; the 4090's harness can run a single role against a
fixture feed over the LAN; a push/pull round trip between the machines
succeeds.

### Step 1 — Collection (`collect/`)

- Implement fetchers, each as an independent script with retry + error
  reporting:
  - **Prices**: free equity price source (e.g. Yahoo Finance via an
    unofficial client, with a fallback source such as stooq) for a
    configurable watchlist (holdings + candidates + SPY benchmark).
  - **Macro**: FRED public API (rates, CPI, unemployment, etc.) for a
    configurable list of series.
  - **News**: RSS feeds (markets, economics, sectors) + light web crawl of
    a small set of allowlisted free pages; store headlines + snippets.
- Storage: **warehouse/raw/** — its own schema: parquet/CSV snapshots per
  fetch + SQLite metadata (source, fetched-at, row count, status).
- systemd timers: prices a few times daily (around market hours), macro
  daily, news every 1–2 hours.

**Done when**: a week of continuous fetching with no manual intervention;
a source outage is visible and recovered automatically.

### Step 2 — Validation (`validate/`)

- Completeness, staleness, schema checks per source →
  **warehouse/validated/** (its own schema: cleaned/verified records +
  validation metadata).
- A machine-readable **data quality report** per run (coverage, staleness,
  failures).
- **Structured failure reports** (error class, stage, source, log excerpt,
  first/last occurrence) for any unrecovered failure — the input to §2.9.

**Done when**: the quality report shows coverage/staleness per source; an
induced failure (e.g. a malformed feed) produces a structured failure
report and an alert.

### Step 3 — Analysis (`analyze/`)

- Deterministic analysis, each an independent module →
  **warehouse/analytics/** (its own schema):
  - **Market snapshot**: price moves, volume, sector performance, notable
    movers, macro indicator readings.
  - **Statistical signals**: correlations, volatility, trend detection,
    signal history with forward-return stats.
  - **Fundamentals**: earnings, valuations, sector rotation, ticker-
    specific news/events.
  - **Macro readings**: FRED series values, upcoming releases, policy
    news.
  - **Risk metrics**: portfolio risk, position/sector exposure, tail
    stats, proposed-limit checks.
- **Per-role feed assembly** (`feeds.py`): each role's bounded feed from
  the analytics (the /feeds/{role} payloads).

**Done when**: a daily run produces all five analytics + per-role feeds
with correct, stable schemas (verified against hand calculations for a
few days).

### Step 4 — Read-only LAN API (`api/`)

- HTTP API bound to the LAN:
  - `GET /feeds/{role}` — per-role feeds (market snapshot, statistical
    signals, fundamentals, macro readings, risk metrics, derived briefs).
  - `GET /quality` — data quality report.
  - `GET /failures` — structured failure reports.
  - `GET /history` — conversation history (rolling window).
  - `POST /recommendation` — the only write endpoint: accepts a team
    recommendation; applies it to the paper portfolio; triggers delivery.
- systemd service; health endpoint; request logging.

**Done when**: all endpoints respond correctly from the 4090 over the LAN;
a posted recommendation is applied to the paper portfolio and delivered.

### Step 5 — Team runtime on the 4090 (`team/`)

- Role definitions: one file per role (mandate, input spec, output schema)
  — structured outputs (JSON) enforced by the session runtime (schema
  validation + bounded retries on malformed output).
- Single-role invocation: given a feed from the 1080, produce the role's
  structured output. Test each role in isolation with real 1080 feeds.
- **Pod manager**: forms **pods** (small groups of 2–3 roles), runs each
  pod as a **separate conversation** (its own transcript/context — no
  cross-pod spillover), and the **Team Lead relays each pod's decision
  into the next pod**; round caps + a Team Lead "close deliberation"
  mechanism.
- Context discipline: per-role **feeds** (bounded, pre-computed on the
  1080) instead of raw dumps — the main defense against context-window
  limits.
- Optional **alternate personality types** (Bull/Bear Analyst, Risk-Averse/
  Aggressive PM, Dovish/Hawkish Economist, ...) spun up during execution
  as structured votes.

**Done when**: a hand-triggered 3-round deliberation on real 1080 feeds
completes with valid structured outputs, stays within model context, and
produces a coherent transcript.

### Step 6 — Simulated portfolio (`portfolio/`)

- SQLite schema: positions, cash, trades, daily marks.
- Seed from `.env` (starting balance in the $5k–$10k regime, optional
  starting positions).
- Paper execution: apply a recommendation (list of actions + sizing) at
  close prices with an assumed transaction cost; fractional-share
  handling; record each decision with the recommendation's rationale.
- Daily mark-to-market job (systemd timer); compute the evaluation metrics
  vs SPY.

**Done when**: a recommendation can be applied, the portfolio marks itself
daily, and the metrics (return, drawdown, Sharpe, vs SPY) are computed
correctly (verify against hand calculations for a few days).

### Step 7 — Pipeline wiring + delivery (1080)

- Wire the autonomous pipeline: collect → validate → analyze → portfolio →
  deliver → archive; stage tracking with resumability.
- Delivery layer: report generator → `reports/`; email on completed runs +
  failures; web dashboard (all views in §2.7 — **no ad-hoc trigger**).
- **Conversation history**: per-session JSONL + markdown in `history/`,
  rolling window, decision journal.

**Done when**: an unattended day of operation produces fresh feeds, a
quality report, and dashboard updates; a posted recommendation is applied,
reported, emailed, and archived with its transcript in history.

### Step 8 — Code sync: auto-pull on the 1080

- systemd timer: `git pull` → **smoke test** (known-good fixture run,
  `SMOKE_TEST_TIMEOUT_S`) → service restart.
- **Auto-revert on failure**: smoke-test failure or post-restart health
  failure → revert to the last known-good commit + alert.
- Last-known-good tracking (tagged commit).

**Done when**: a push from the 4090 is applied on the 1080 within one
timer interval; a deliberately broken push is auto-reverted with an alert,
and the pipeline keeps serving.

### Step 9 — Role-scoped self-modification loop (failures + feature requests)

- **Failures**: reports from /failures → the matching role session on the
  4090 (per its edit scope, §2.2) → diagnosis → fix within that role's
  scope only → tagged commit + push → 1080 auto-pull + smoke test → verify
  or auto-revert.
- **Feature requests / ideas**: a pod decides a new capability is needed →
  the role with the matching edit scope implements it in its own scope
  (e.g. the Quant asks for a model → the MLE or Data Scientist updates
  `analyze/`) → tagged commit + push → 1080 auto-pull + smoke test → verify
  the capability works or auto-revert.
- Guardrails (§2.9): per-role bounded scope, smoke-test gate, auto-revert,
  change log, escalation on repeated fixes / non-working features.

**Done when**: an induced fetcher bug (e.g. a changed feed format) is
diagnosed and fixed end-to-end by the loop, with a tagged commit, a change-
log entry, and a verified 1080 run — a second induced regression is caught
by the smoke-test gate and auto-reverted — AND a feature request (e.g. a
new model) is implemented end-to-end by the matching role, verified, and
appears in the 1080's feeds.

### Step 10 — Ad-hoc team sessions

- User-triggered from the DeepSeek harness: goal/prompt → role selection
  (auto or manual) → fetch feeds from the 1080 → deliberate → POST
  /recommendation → delivery + history.
- Ad-hoc sessions are recorded in conversation history exactly like any
  other session.

**Done when**: an ad-hoc question produces a delivered answer using
current 1080 data, without disturbing the autonomous pipeline.

### Step 11 — Hardening & docs

- Retries, timeouts, and degradation paths for every external dependency
  (sources, SMTP, dashboard, API).
- Archive size caps (oldest deleted first), log rotation.
- Monitoring: a simple health view (fetch freshness, last run, disk usage,
  4090 reachability).
- Write `README.md` + `SETUP.md` (deployment guide, mirroring the
  `LLM_Server` style), including the update flow (4090 push → 1080
  auto-pull → smoke test).

**Done when**: a fresh-machine deployment from the docs succeeds; a week of
unattended operation with no manual fixes.

### Step 12 — Evaluation loop (run the weeks)

- Run sessions over several weeks; review the paper-portfolio performance
  vs SPY and the per-decision record (decision journal).
- Tune roles/prompts based on observed failures (hallucinated numbers,
  shallow analysis, overtrading, non-convergence) — using the conversation
  history as the evidence base.
- Document what the team got right/wrong — this informs Phase B readiness.

**Done when**: a written evaluation of the first N weeks exists, with
concrete prompt/pipeline changes applied and re-verified.

### Step 13 — Phase B/C (real portfolio, deferred)

- Phase B: choose the brokerage connection (Alpaca / IBKR / CSV import),
  implement a **read-only** holdings fetcher in `collect/`, run
  recommendations against real positions.
- Phase C: proposed-order flow with dashboard/email approval, paper
  trading first, strict limits, kill switch.

(See §5 for the detailed next steps.)

---

## 4. Concerns with the Initial Version

Each concern lists the risk and the planned mitigation.

### 4.1 Local-model quality ceiling

Qwen 3.8 on the 4090 is a strong local model, but still far weaker than
frontier models. The team may produce plausible-sounding but shallow,
overconfident, or internally inconsistent analyses, and the "debate" may be
more performance than substance.

**Mitigation**: the two-machine split puts the best model the hardware can
run on the reasoning-heavy roles (§2.2); structured outputs forced on
every role; the Data Scientist's math lives in code on the 1080 and is
grounded in actual numbers from the feeds; the Challenger exists
specifically to break shallow consensus; the Risk Manager enforces the
risk policy deterministically; the Team Lead verifies convergence before
sign-off; the paper-portfolio evaluation loop (§3 Step 12) is the honest
test — if the team's decisions don't hold up against SPY and the decision
record, the prompts/roles change. Output is decision support, not answers.

### 4.2 Hallucinated data

Roles may cite prices, statistics, or "facts" that are not in the fetched
dataset. This is the classic LLM failure mode and is dangerous in a
financial context.

**Mitigation**: roles receive **only** the 1080's feeds (no raw web access
during analysis); outputs require references to data keys/fields; a
validation pass checks numeric claims against the warehouse; the Data
Engineer's quality report is the team's ground truth for what is known.

### 4.3 Context-window limits

Qwen 3.8 has a large context budget, but full transcripts plus data
snapshots still will not fit, and long sessions degrade.

**Mitigation**: per-role bounded feeds (pre-computed on the 1080, not
raw); summarization between deliberation rounds; hard round caps; context
assembly that includes agenda + recent rounds + only the digests relevant
to the speaker. The conversation manager (and the harness's own context
management) enforces the budget and truncates deterministically.

### 4.4 Free data-source fragility

Unofficial price APIs (e.g. Yahoo Finance), RSS feeds, and crawled pages
break, change format, or rate-limit. A silent data gap would poison the
whole run.

**Mitigation**: a fallback source per data type; caching so a single
missed fetch doesn't lose data; staleness thresholds in the data quality
report; fetch failures are visible (dashboard + alert) and never silently
skipped. The Data Engineer role explicitly reports coverage gaps so the
team reasons with known-unknowns. The self-modification loop (§2.9) can fix
recurring fetcher breakage without manual intervention.

### 4.5 Session duration and compute

A full team session (9 roles × analyses + multiple deliberation rounds) on
Qwen 3.8 on the 4090 takes tens of minutes (order of 30–90 min). Sessions
are ad-hoc, so there is no weekly batch deadline — but long sessions are
still a wall.

**Mitigation**: sessions run with a multi-hour wall-clock budget; stages
are resumable; the pipeline reports progress per stage so a stuck session
is diagnosable. If sessions are consistently too slow, round count is
tuned — not the deadline. The 4090 is idle otherwise, so compute is not
shared.

### 4.6 Deliberation non-convergence

Agent teams can talk in circles: endless challenge/revise cycles, or the
Team Lead failing to close.

**Mitigation**: hard round budget per session; Team Lead has explicit
authority (and a structured "close" output) to end deliberation; deadlock
detection (no substantive change between rounds) forces a close; the final
recommendation is always produced even if convergence was partial — with
the Team Lead's notes stating what was unresolved.

### 4.7 Overtrading in the paper portfolio

The team may recommend frequent position changes; churn with transaction
costs will make the paper P&L look bad and may reflect prompt behavior
rather than insight.

**Mitigation**: an assumed transaction cost on every paper trade; turnover
limits stated in the Portfolio Manager role's mandate; the Risk Manager
checks turnover against the risk policy; trade count/turnover tracked as a
first-class metric; the evaluation loop (§3 Step 12) explicitly reviews
churn. At the $5k–$10k scale, costs are proportionally more visible —
churn hurts the P&L in a way that is hard to miss.

### 4.8 Dashboard + API + email exposure

The dashboard and the read-only API are reachable by anyone on the network
who knows the URL (per the current plan) and contain the user's portfolio
details and strategy. v1 has no authentication.

**Mitigation (light, v1)**: bind to LAN only (no public exposure); use a
non-guessable port/path; treat the content as "internal to the home
network." The API is read-only (the only write is POST /recommendation,
which only affects the paper portfolio). **Planned (early)**: a simple
shared token (query param or login) and, if remote access is ever wanted,
Tailscale (consistent with `LLM_Server`) rather than exposing the port.
Email: use an authenticated SMTP account; the report contains no secrets
beyond portfolio data.

### 4.9 Evaluation validity

A few weeks of paper performance is not meaningful statistical evidence.
Early wins or losses should not be over-read — the sample is tiny and the
market regime matters.

**Mitigation**: the paper portfolio is framed as an **evaluation vehicle**,
not a prediction; the per-decision record (decision + rationale + outcome)
is the more useful artifact than the P&L curve; Phase B is gated on
decision-quality review, not on a P&L target.

### 4.10 On-demand availability (1080 + 4090)

Both the 1080 (woken by WOL) and the 4090 (user-powered) are on-demand —
only the Pi is always-on. If either is asleep/off, the user cannot run a
team session. (The autonomous 1080 data cycle is driven by the Pi's
scheduled WOL, so it does not depend on the 4090.)

**Mitigation**: the **Pi is the always-on anchor** — it reliably runs the
scheduled WOL to keep the 1080's data fresh on schedule. For ad-hoc
sessions: the user powers the 4090 on when they want a session (no wake
machinery to maintain), and a WOL wakes the 1080 so it can serve feeds;
the dashboard shows 1080 + 4090 reachability in real time so the user
knows before starting; the autonomous cycle keeps data fresh in the
meantime, so a session started later still runs against current data;
failure alerts from the 1080 are queued in /failures for the self-modification loop
loop when the 4090 is back.

### 4.11 Self-modification risk (harness → repo → 1080)

The DeepSeek harness is a coding-agent runtime and can modify the shared
repo — meaning it can change the 1080's pipeline. An unguarded
self-modification loop could break the always-on data engine or, worse,
"fix" things in ways that silently change what the team sees.

**Mitigation**: the sanctioned path is the **role-scoped self-modification loop**
(§2.9) with its guardrails — **per-role bounded scope** (each role is
limited to its own scope — ingestion / ETL / analysis — per §2.2),
smoke-test gate, auto-revert, tagged commits + change log, escalation on
repeated fixes. The 1080's auto-pull timer is the only entry point for
4090 code changes, and it never keeps code that fails the smoke test. The
portfolio/delivery/api/team packages are out of scope for self-modification by
construction.

### 4.12 1080 8 GB VRAM ceiling

The 1080 has 8 GB VRAM — too small for a quality LLM. Any design that
assumes an LLM on the 1080 is dead on arrival.

**Mitigation**: the 1080 is **deterministic-only by design** — no stage
needs an LLM, so the ceiling is irrelevant to the pipeline. All reasoning
lives on the 4090. If an LLM on the 1080 is ever wanted (e.g. small-model
text summarization), that is a hardware decision, not a pipeline change —
the segregated design means a future LLM stage would slot in without
restructuring.

### 4.13 WOL reliability & the Pi anchor

The whole 1080 data cycle depends on the Pi's WOL waking the 1080. If the
WOL fails (NIC offload quirks, sleep-state issues, a network change), the
1080 stays asleep and the data goes stale.

**Mitigation**: the Pi verifies each WOL (does the 1080 come up within a
timeout?) and retries; a missed wake is surfaced as an alert (email +
dashboard) so the user knows the 1080 did not run; the Pi is a small
always-on device (low power, low maintenance) precisely to be the
reliable anchor; the 1080's data freshness is shown on the dashboard so a
stale 1080 is visible even if the WOL failed.

---

## 5. Future Improvements & Next Steps

Each improvement has a clear description and concrete next steps.

### 5.1 Phase B — Real portfolio, read-only

**Description**: Connect the user's actual holdings so the team recommends
against real positions (without executing). This is the bridge from
"evaluation" to "useful."

**Next steps**:
1. Shortlist connections: **Alpaca API** (simple, paper-account-capable,
   good docs), **IBKR API** (powerful, more setup), or a **CSV import** of
   brokerage statements as a zero-API intermediate step.
2. Pick one; implement a read-only holdings fetcher (positions, cash, cost
   basis) in `collect/`, with the same quality checks as other sources.
3. Add a "real portfolio" view to the dashboard (holdings + latest
   recommendation mapped onto them); keep the paper portfolio running in
   parallel for comparison.
4. Gate: run for 2–4 weeks; verify recommendations are sensible against
   real positions before considering execution.

### 5.2 Phase C — Automated execution with human-in-the-loop

**Description**: Turn the recommendation into a proposed order set that the
user approves before placement. Paper trading first, then live with strict
limits.

**Next steps**:
1. Implement the order-proposal flow: recommendation → normalized orders
   (ticker, side, quantity, limit) → pending-approval state.
2. Approval UI: dashboard approve/reject (and email with a reply mechanism
   as a fallback).
3. Execute via the chosen brokerage API in **paper mode** (e.g. Alpaca
   paper trading) until the approval/execution path is proven.
4. Add guardrails before any live trading: max order size, allowed-ticker
   list, daily/weekly trade caps, and a global kill switch.
5. Only then consider live orders — and keep the human approval step.

### 5.3 More and better data sources

**Description**: Widen the team's evidence base beyond prices/macro/news.

**Next steps** (each is a standalone fetcher in `collect/` + a digest in
`analyze/`):
1. **Earnings calendar** (free sources) — events that dominate the coming
   week for holdings.
2. **Economic calendar** (Fed decisions, CPI, jobs) — complements FRED
   series with *upcoming* dates.
3. **Options/flow signals** where freely available (e.g. put/call ratios)
   — with the Data Scientist's skepticism applied.
4. **Crypto** (CoinGecko, free) if the user ever wants crypto exposure —
   prices + simple sentiment.
5. **Alternative text sources**: Fed statements, central-bank minutes,
   allowlisted research blogs — crawl + store, fed to the Economist/
   Financial Analyst digests.

### 5.4 Better evaluation & prompt tuning

**Description**: Make the loop between "team decision" and "what happened"
tighter, so roles improve over time.

**Next steps**:
1. Build the **decision journal** view: each recommendation with rationale,
   confidence, and the subsequent outcome (price moves, P&L impact) —
   assembled from conversation history (§2.10).
2. Track **hit-rate metrics**: how often the team's directional calls and
   risk calls were right; where they systematically err.
3. Add **backtest-style checks**: for recurring rules the team proposes
   ("trim on X signal"), have the Data Scientist compute historical
   performance from the warehouse before the rule is adopted.
4. Maintain a **prompt changelog**: every role-prompt change with the
   observed failure that motivated it and the before/after decision
   quality.

### 5.5 Role composition & duplicate personalities

**Description**: Extend the team's composition: more roles, and
**duplicate personalities** — two roles with the same base mandate but
opposite perspectives, run as a structured vote.

**Next steps**:
1. **Bull Analyst / Bear Analyst**: two Financial Analysts with opposite
   mandates (the best case for the thesis vs. the best case against it).
2. **Risk-Averse PM / Aggressive PM**: two Portfolio Managers with
   different risk profiles; the base PM's recommendation is the synthesis.
3. The Team Lead runs the duplicates as a structured vote (each presents,
   then the Team Lead records the split) before convergence.
4. Make role composition a per-session config (which roles + which
   duplicates run) — cheap to add, valuable for A/B'ing team shapes.
5. Revisit model specialization per role (e.g. a faster model for the
   duplicates) when the harness supports per-role model targets.

### 5.6 Long-term team memory

**Description**: Give the team persistent memory of its own past decisions
and outcomes, so session N+1's deliberation is informed by what session N
got right or wrong.

**Next steps**:
1. Define a **memory digest**: recent decisions, outcomes, unresolved
   disagreements, and the Team Lead's post-session notes — assembled from
   **conversation history** (§2.10) + the decision journal.
2. Inject it as standing context at the start of each session.
3. Keep it bounded (the last N sessions) to respect context limits; the
   archives remain the full record.
4. Evaluate: does the team reference and learn from its memory in
   transcripts? If not, restructure the memory format.

### 5.7 Dashboard hardening & remote access

**Description**: Protect and extend the delivery surface.

**Next steps**:
1. Add the shared-token auth (see §4.8 mitigation) — small effort, early
   win. Cover both the dashboard and the read-only API.
2. If off-network access is wanted: put the dashboard + API behind
   **Tailscale** (consistent with `LLM_Server`) rather than exposing the
   port.
3. Add a **run history** view (every session, status, duration, link to
   transcript) — built on conversation history.
4. Add **data-source health** per fetcher (success rate, last success, row
   counts over time).

### 5.8 Voice interface (optional, fun)

**Description**: Let the user talk to the team through the existing
`LLM_Server` Mumble setup — e.g. ask the team a question by voice and get
the answer in the channel, reusing the tower pipeline.

**Next steps**:
1. Expose the ad-hoc session as a small HTTP endpoint (prompt → result)
   that the 4090's harness can call.
2. From the LLM_Server side, route a channel message matching a trigger
   (e.g. "portfolio: ...") to that endpoint.
3. Return the recommendation summary as a channel text message.
4. Treat this as a convenience layer — the harness remains the primary
   interface for sessions.

### 5.9 Deterministic risk engine

**Description**: Move risk math out of LLM judgment into code: position
limits, correlation checks, drawdown guards, VaR-style estimates — computed
deterministically on the 1080 and presented to the team as constraints.

**Next steps**:
1. Define the risk policy (max position %, max sector %, max turnover,
   stop-loss/drawdown rules) in config.
2. Implement the checker in `analyze/` (risk metrics): given a proposed
   recommendation, compute violations; the Risk Manager must surface them
   and the Portfolio Manager must address them before sign-off.
3. Show the risk report on the dashboard alongside the recommendation.
4. The LLM proposes; the engine constrains — this is the strongest defense
   against overconfident or reckless recommendations.

### 5.10 Multi-portfolio / user profiles

**Description**: Support multiple portfolio profiles (different risk
tolerances, horizons, constraints) so the same team can serve more than
one scenario — e.g. a conservative and an aggressive version of the same
holdings.

**Next steps**:
1. Generalize the portfolio store to multiple named portfolios (schema
   change; paper portfolio becomes one of them).
2. Add a **risk profile** to each portfolio (tolerance, constraints) that
   is injected into the Portfolio Manager's mandate.
3. Run the team once per portfolio per session (sequentially, to share
   analysis work).
4. Dashboard: side-by-side comparison of profiles.

### 5.11 Self-modification hardening

**Description**: Harden the role-scoped self-modification loop (§2.9) from a
working v1 into a trustworthy automation.

**Next steps**:
1. **Wider smoke-test fixtures**: per-source fixture runs (prices, macro,
   news) so the gate catches source-specific regressions, not just
   pipeline-wide ones.
2. **Sandboxed test branch**: self-modification commits land on a `self-mod`
   branch first; the 1080 pulls the branch, smoke-tests, and only merges
   to main on a green gate.
3. **Self-modification metrics**: fix rate, revert rate, feature-implementation rate, time-to-fix, per-failure-
   class counts — shown on the dashboard; a rising revert rate is an
   escalation signal.
4. **Regression memory**: each fixed failure is recorded (failure
   signature → fix commit) so the Data Engineer can recognize recurring
   breakage and reference the prior fix.
5. **Scope review**: periodically review whether the bounded scope
   (collect/validate/analyze) is right — e.g. whether api/ feed-assembly
   bugs should ever be in scope.

---

## Appendix A — Segregated repository layout (v1)

```
Portfolio_Manager/
├── README.md                    # purpose + quick start (written in Step 11)
├── SETUP.md                     # deployment guide (written in Step 11)
├── .gitignore                   # .env, .venv/, warehouse/, history/, archives/
├── .env.example                 # all configuration with placeholders
├── requirements.txt
├── collect/                     # collection package (Step 1) — its own schema
│   ├── prices.py
│   ├── macro_fred.py
│   ├── news_rss.py
│   └── raw/                     # warehouse/raw (generated): raw fetch schema
├── validate/                    # validation package (Step 2) — its own schema
│   ├── checks.py
│   ├── quality.py               # data quality report
│   ├── failures.py              # structured failure reports
│   └── validated/               # warehouse/validated (generated)
├── analyze/                     # analysis package (Step 3) — its own schema
│   ├── snapshot.py              # market snapshot
│   ├── signals.py               # statistical signals
│   ├── fundamentals.py
│   ├── macro.py                 # macro readings
│   ├── risk.py                  # risk metrics
│   ├── feeds.py                 # per-role feed assembly
│   └── analytics/               # warehouse/analytics (generated)
├── workflows/                   # algorithmic workflows (MLE, new): feature stores,
│   │                            # model training/serving, orchestration, monitoring
│   ├── features/
│   ├── models/
│   └── orchestration/
├── portfolio/                   # simulated portfolio (Step 6)
│   ├── db.py
│   ├── execute.py               # paper execution + transaction costs
│   └── metrics.py               # P&L, drawdown, Sharpe, vs SPY
├── delivery/                    # report, email, dashboard (Step 7)
│   ├── report.py
│   ├── email.py
│   └── dashboard/
├── api/                         # read-only LAN HTTP API (Step 4)
│   ├── server.py
│   └── routes/
├── team/                        # LLM team runtime (4090 harness, Step 5)
│   ├── roles/
│   │   ├── team_lead.py
│   │   ├── data_engineer.py
│   │   ├── data_analyst.py
│   │   ├── data_scientist.py
│   │   ├── financial_analyst.py
│   │   ├── economist.py
│   │   ├── risk_manager.py
│   │   ├── challenger.py
│   │   ├── portfolio_manager.py
│   │   ├── mle.py               # Machine Learning Engineer
│   │   └── quant.py             # Quantitative Researcher
│   ├── alternates/              # alternate personality types spun up during execution
│   │   ├── bull_analyst.py
│   │   ├── bear_analyst.py
│   │   ├── dovish_economist.py
│   │   ├── hawkish_economist.py
│   │   ├── risk_averse_pm.py
│   │   ├── aggressive_pm.py
│   │   └── ...                  # (per-role alternates, see §2.2)
│   ├── pods.py                  # pod manager: forms pods, runs each as a separate
│   │                            # conversation (no cross-pod spillover); the Team
│   │                            # Lead relays each pod's decision into the next
│   ├── session.py               # ad-hoc session: fetch feeds -> deliberate in pods
│   │                            # -> return (or raise a feature request)
│   └── self_mod.py              # role-scoped self-modification loop (Step 9):
│                                # failures + feature requests, per-role scope
├── history/                     # conversation history (Step 7): per-session JSONL + md
├── archives/                    # permanent size-capped record (generated)
├── reports/                     # markdown reports + change log (generated)
└── systemd/                     # service + timer units (incl. auto-pull)
```

Deployment: the **Pi** (always-on) runs the scheduled WOL. The **1080
machine** (woken by WOL) runs all services + timers (including the
auto-pull timer) while awake. The **4090 machine** runs the DeepSeek
harness + a repo checkout (the team runtime and the self-modification loop need
the repo).

## Appendix B — Key configuration (`.env` sketch)

| Variable | Meaning |
|---|---|
| `WATCHLIST` | Tickers to fetch (holdings + candidates + SPY) |
| `FRED_SERIES` | FRED series IDs for the macro digest |
| `NEWS_FEEDS` | RSS feed URLs (comma-separated) |
| `API_HOST` / `API_PORT` | 1080 read-only API bind (LAN; default 0.0.0.0:8400) |
| `WOL_TARGET_MAC` / `WOL_TARGET_IP` | The 1080's MAC/IP for WOL (woken by the Pi) |
| `WOL_SCHEDULE` | The Pi's scheduled WOL cadence (e.g. "daily 06:00") |
| `WOL_TIMEOUT_S` | How long the Pi waits for the 1080 to come up after a WOL |
| `PI_HOST` | The always-on Pi's address (WOL service config) |
| `PORTFOLIO_START_BALANCE` | Paper portfolio starting cash ($5,000–$10,000 regime; default $10,000) |
| `PORTFOLIO_START_POSITIONS` | Optional starting positions (ticker:shares) |
| `TX_COST_BPS` | Assumed transaction cost (basis points) on paper trades |
| `BENCHMARK_TIKER` | Benchmark for evaluation (default SPY) |
| `SESSION_TIMEOUT_HOURS` | Wall-clock budget for a team session |
| `DELIBERATION_MAX_ROUNDS` | Hard round cap for ideation sessions |
| `POD_MAX_ROLES` | Max roles per pod (default 3) |
| `POD_MAX_PODS` | Max pods per session (default 5) |
| `HISTORY_WINDOW_SESSIONS` / `HISTORY_CAP_MB` | Rolling window for conversation history (count + size cap) |
| `AUTOPULL_INTERVAL_MIN` | 1080 auto-pull timer interval (git pull → smoke test → restart) |
| `SMOKE_TEST_TIMEOUT_S` | Smoke-test budget for auto-pull |
| `SELF_MOD_MAX_ESCALATIONS` | Threshold before the self-modification loop (failures + feature requests) escalates + pauses |
| `REPO_REMOTE_URL` | Private git remote for 4090 → 1080 code sync |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `EMAIL_TO` | Email delivery |
| `DASHBOARD_HOST` / `DASHBOARD_PORT` | Dashboard bind (LAN) |
| `ARCHIVE_CAP_GB` | Size cap per archive (oldest deleted first) |

Note: the harness/model configuration (Qwen 3.8 model tag, harness runtime
options) lives on the 4090 side in the harness's own config, and the Pi's
WOL service configuration lives on the Pi side — neither is in this repo's
`.env`.
