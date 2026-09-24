"""Per-role feed assembly (Step 3) — each role's bounded feed from the
analytics. This is the main defense against context-window limits
(outline §4.3): roles receive bounded, pre-computed digests — never raw
dumps — and only within their data tier (outline §2.2):

  raw:      data the role can read as-is (warehouse)
  derived:  digests computed in code (snapshot, signals, fundamentals,
            macro readings, risk metrics)
  briefs:   derived briefs (quality report, data gaps, agenda)

The /feeds/{role} payloads are these JSONs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from common import config
from validate import quality as vquality

ANALYTICS_DIR = config.ANALYTICS_DIR

# role -> (data tier, edit scope) — mirrors outline §2.2
ROLE_META = {
    "team_lead": ("briefs", "none"),
    "data_engineer": ("raw", "ingestion (collect/)"),
    "data_analyst": ("raw", "analysis (analyze/)"),
    "data_scientist": ("raw", "ETL (validate/) + analysis (analyze/)"),
    "financial_analyst": ("derived", "analysis (analyze/)"),
    "economist": ("derived", "analysis (analyze/)"),
    "risk_manager": ("derived", "analysis (analyze/)"),
    "challenger": ("derived", "analysis (analyze/)"),
    "portfolio_manager": ("briefs", "none"),
    "mle": ("raw", "analysis (analyze/) + workflow code (workflows/)"),
    "quant": ("raw", "analysis (analyze/)"),
}


def _latest(kind: str) -> dict | None:
    d = ANALYTICS_DIR / kind
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _quality_brief() -> dict:
    rep = vquality.load_report()
    if rep is None:
        return {"available": False}
    return {
        "available": True,
        "generated_at": rep.get("generated_at"),
        "summary": rep.get("summary"),
        "coverage": rep.get("coverage"),
        "data_gaps": sorted(
            {r.get("error", "") for r in rep.get("sources", {}).values() if r.get("status") != "ok"}
        ),
        "open_failure_ids": rep.get("open_failure_ids", []),
    }


def _failure_brief() -> list[dict]:
    from common import failures as cf

    return [
        {
            "failure_id": r.failure_id,
            "error_class": r.error_class,
            "stage": r.stage,
            "source": r.source,
            "message": r.message,
            "occurrence_count": r.occurrence_count,
        }
        for r in cf.open_reports()
    ]


def _clip(obj, max_items: int = 25):
    """Bound list lengths so a feed can never balloon the context."""
    if isinstance(obj, list):
        return obj[:max_items]
    if isinstance(obj, dict):
        return {k: _clip(v, max_items) for k, v in obj.items()}
    return obj


def build_feed(role: str) -> dict:
    if role not in ROLE_META:
        raise ValueError(f"unknown role: {role}")
    tier, scope = ROLE_META[role]
    feed: dict = {
        "role": role,
        "data_tier": tier,
        "edit_scope": scope,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quality": _quality_brief(),
    }

    snapshot = _latest("snapshot")
    signals = _latest("signals")
    fund = _latest("fundamentals")
    macro = _latest("macro")
    risk = _latest("risk")

    if role == "data_engineer":
        feed["failure_reports"] = _failure_brief()
        feed["source_status"] = (
            vquality.load_report() or {"sources": {}}
        ).get("sources", {})
        feed["data"] = {"tier": "raw", "note": "raw warehouse access (collect/raw) + quality/failure reports"}
    elif role in ("data_analyst",):
        feed["data"] = {"market_snapshot": _clip(snapshot), "tier": "raw + derived"}
    elif role in ("data_scientist", "mle"):
        feed["data"] = {
            "statistical_signals": _clip(signals),
            "market_snapshot": _clip(snapshot, 10),
            "tier": "raw + derived",
        }
        if role == "mle":
            feed["data"]["workflow_state"] = "workflows/ (feature stores, models) — see the repo"
    elif role == "financial_analyst":
        feed["data"] = {"fundamentals": _clip(fund), "tier": "derived + ticker news"}
    elif role == "economist":
        feed["data"] = {"macro_readings": _clip(macro), "tier": "derived + FRED values"}
    elif role == "risk_manager":
        feed["data"] = {"risk_metrics": _clip(risk), "tier": "derived + briefs"}
    elif role == "challenger":
        # derived counter-evidence: the bearish half of the digests
        counter = {}
        if signals:
            bearish = [
                a for a in signals.get("assets", [])
                if (a.get("max_drawdown_60d_pct") or 0) < -10
                or (a.get("momentum_20d_pct") or 0) < 0
                or (a.get("volatility_20d_ann_pct") or 0) > 30
            ]
            counter["bearish_signals"] = bearish
        if risk:
            counter["limit_violations"] = risk.get("limit_checks", [])
            counter["tail_stats"] = risk.get("asset_tail_stats", [])
        if snapshot:
            counter["data_gaps"] = snapshot.get("data_gaps", [])
        feed["data"] = {"counter_evidence": _clip(counter), "tier": "briefs + derived counter-evidence"}
    elif role == "quant":
        feed["data"] = {
            "statistical_signals": _clip(signals),
            "signal_history": (signals or {}).get("signal_history", {}),
            "market_snapshot": _clip(snapshot, 10),
            "tier": "raw + derived (historical warehouse for backtests)",
        }
    else:  # team_lead, portfolio_manager — briefs only
        brief = {}
        if snapshot:
            brief["market_highlights"] = {
                "notable_movers": snapshot.get("notable_movers", []),
                "sector_performance": snapshot.get("sector_performance", {}),
                "data_gaps": snapshot.get("data_gaps", []),
            }
        if role == "portfolio_manager":
            brief["risk_summary"] = {
                "limit_checks": (risk or {}).get("limit_checks", []),
                "portfolio": (risk or {}).get("portfolio"),
            }
        feed["data"] = {"briefs": _clip(brief), "tier": "briefs"}

    return feed


def write_feed(role: str) -> Path:
    d = ANALYTICS_DIR / "feeds" / role
    d.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = d / f"{day}.json"
    p.write_text(json.dumps(build_feed(role), indent=2), encoding="utf-8")
    return p


def all_roles() -> list[str]:
    return list(ROLE_META.keys())
