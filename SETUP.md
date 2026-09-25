# Setup

## 1080 (Linux, systemd)

```bash
git clone <private-remote> /opt/portfolio_manager
cd /opt/portfolio_manager
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # fill in: FRED_API_KEY, SMTP_*, FEED_API_BASE,
                            # TEAM_RUNTIME_HEALTH_URL (the 4090's health URL)
```

Units:

```bash
cp systemd/pm-*.service systemd/pm-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pm-api.service
systemctl enable --now pm-collect-prices.timer pm-collect-macro.timer pm-collect-news.timer
systemctl enable --now pm-validate.timer pm-analyze.timer pm-portfolio-mark.timer
systemctl enable --now pm-pipeline.timer
systemctl enable --now pm-autopull.timer
systemctl enable --now pm-maintenance.timer
```

Verify:

```bash
systemctl list-timers | grep pm-
curl -s localhost:8400/quality
curl -s localhost:8400/feeds/team_lead | head
curl -s localhost:8300/api/status
```

## 4090 (Windows)

```powershell
git clone <private-remote> D:\LLM\Portfolio_Manager
cd D:\LLM\Portfolio_Manager
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # fill in: KOBOLDCPP_URL, FEED_API_BASE (the 1080's API)
```

Local model (koboldcpp) on `localhost:5001` (see the koboldcpp docs for the
exact launch command for your build). Then:

- **Health endpoint:** `python -m team.health` (port 8500; set
  `TEAM_RUNTIME_HEALTH_URL=http://<4090-ip>:8500/health` in the 1080's `.env`)
- **Test one role:** `python -m team.invocation team_lead`
- **Run a session:** `python -m team.session --rounds 3 --post`
- **Ad-hoc session:** `python -m team.session --roles quant,challenger,risk_manager`
- **Free-form goal:** `python -m team.session --goal "analyze the semiconductor sector"`
- **Self-mod (nightly):** `python -m team.self_mod`

Nightly self-mod via Task Scheduler:

```
schtasks /create /tn "PM-SelfMod" /tr "D:\LLM\Portfolio_Manager\.venv\Scripts\python.exe -m team.self_mod" /sc daily /st 02:00
```

## Pi (optional)

Wake-on-LAN for the 4090 (requires the 4090's MAC + WOL enabled in its
BIOS). Verify with your WOL utility of choice.

## Smoke test (either machine)

```bash
python -m workflows.smoketest
```

Imports every package and builds both FastAPI apps. This is the gate the
1080's autopull uses before accepting 4090 commits (and the gate the
self-mod loop uses before pushing fixes).

## Failure behavior

- A failed collect source → failure report + email; the run continues
  (partial data), the quality report shows the gap.
- A failed pipeline stage → run halts, state recorded, failure email sent.
- A bad 4090 commit → autopull smoke-fails, `git reset --hard` to the
  previous HEAD.
- A bad self-mod fix → reverted, escalation counter +1; at 3 escalations
  the loop stops and emails.
