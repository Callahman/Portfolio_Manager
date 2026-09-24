"""Report generation (Step 7) — markdown report to reports/.

Contents: data quality summary, each role's analysis (from the analytics),
deliberation highlights (from the latest session), final recommendation,
paper-portfolio impact. Also appends to reports/change_log.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from common import config
from validate import quality as vquality
from portfolio import metrics as pmetrics
from portfolio import db as pdb

REPORTS_DIR = config.REPORTS_DIR
CHANGE_LOG = REPORTS_DIR / "change_log.md"


def _section(title: str, lines: list[str]) -> str:
    return f"## {title}\n\n" + "\n".join(lines) + "\n"


def build_report(rec: dict | None = None, result: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    parts: list[str] = [f"# Portfolio Manager — {day} {now.strftime('%H:%M')} UTC\n"]

    # data quality summary
    q = vquality.load_report()
    if q:
        s = q.get("summary", {})
        lines = [
            f"generated {q.get('generated_at')} — {s.get('ok', 0)}/{s.get('total_sources', 0)} sources ok, "
            f"{s.get('stale', 0)} stale, {s.get('failed', 0)} failed",
            f"coverage: {json.dumps(q.get('coverage', {}))}",
        ]
        bad = [
            f"- {src}: {r.get('status')} — {r.get('error')}"
            for src, r in q.get("sources", {}).items()
            if r.get("status") != "ok"
        ]
        lines.extend(bad or ["- all sources ok"])
        parts.append(_section("Data quality", lines))

    # each role's analysis (from the analytics)
    role_analyses = {
        "Data Analyst (market snapshot)": "snapshot",
        "Data Scientist (statistical signals)": "signals",
        "Financial Analyst (fundamentals)": "fundamentals",
        "Economist (macro readings)": "macro",
        "Risk Manager (risk metrics)": "risk",
    }
    for title, kind in role_analyses.items():
        p = config.ANALYTICS_DIR / kind / f"{day}.json"
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        summary = {k: v for k, v in data.items() if k not in ("assets", "tickers", "series", "sources")}
        parts.append(
            _section(
                title,
                [f"- {k}: {json.dumps(v)[:200]}" for k, v in list(summary.items())[:6]],
            )
        )

    # final recommendation
    if rec:
        actions = rec.get("actions", [])
        lines = [f"rationale: {rec.get('rationale', '(none)')}"]
        for a in actions:
            lines.append(
                f"- {a.get('side')} {a.get('shares')} {a.get('ticker')} — {a.get('rationale', '')}"
            )
        if result:
            lines.append(f"executed: {len(result.get('executed', []))} actions; cash after: {result.get('cash_after')}")
        parts.append(_section("Final recommendation", lines))

    # paper-portfolio impact
    try:
        m = pmetrics.compute_metrics()
        if m.get("available"):
            b = m.get("benchmark", {})
            parts.append(
                _section(
                    "Paper portfolio",
                    [
                        f"total: ${m.get('total')} (as of {m.get('as_of')})",
                        f"cumulative return: {m.get('cumulative_return_pct')}% "
                        f"(benchmark {b.get('cumulative_return_pct')}%, excess {b.get('excess_return_pct')}%)",
                        f"max drawdown: {m.get('max_drawdown_pct')}% "
                        f"(benchmark {b.get('max_drawdown_pct')}%)",
                        f"Sharpe (ann): {m.get('sharpe_ann')}; trades: {m.get('n_trades')}; turnover: {m.get('turnover')}",
                    ],
                )
            )
    except Exception:  # noqa: BLE001
        pass

    return "\n".join(parts)


def write_report(rec: dict | None = None, result: dict | None = None) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = REPORTS_DIR / f"{day}.md"
    p.write_text(build_report(rec, result), encoding="utf-8")
    _append_change_log(rec, p)
    return p


def _append_change_log(rec: dict | None, report_path: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n_actions = len(rec.get("actions", [])) if rec else 0
    with CHANGE_LOG.open("a", encoding="utf-8") as f:
        f.write(f"- {now}: report written ({report_path.name}); recommendation with {n_actions} actions\n")
