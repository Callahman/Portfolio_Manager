# systemd units (1080)

These units run on the 1080 machine (Linux) while it is awake (woken by WOL
from the Pi). The repo checkout lives at `/opt/portfolio_manager` (adjust
the `WorkingDirectory`/`ExecStart` paths if yours differs).

## Install

```bash
sudo cp /opt/portfolio_manager/systemd/pm-*.service /opt/portfolio_manager/systemd/pm-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pm-collect-prices.timer pm-collect-macro.timer pm-collect-news.timer
# add the remaining units (validate, analyze, portfolio-mark, api, dashboard, autopull) as their epics land
```

## Units by epic

| Epic | Units |
|---|---|
| 1 (collect) | `pm-collect-prices.*`, `pm-collect-macro.*`, `pm-collect-news.*` |
| 2 (validate) | `pm-validate.*` |
| 3 (analyze) | `pm-analyze.*` |
| 4 (api) | `pm-api.service` |
| 6 (portfolio) | `pm-portfolio-mark.*` |
| 7 (delivery) | `pm-dashboard.service` |
| 8 (auto-pull) | `pm-autopull.*` |

Note: the 1080 is not always-on — timers only fire while the machine is
awake. `Persistent=true` catches up missed runs after the next WOL wake.
