"""Macro readings (Step 3) — FRED series values, frequency, changes,
upcoming releases (best-effort from the FRED release calendar), and policy
news from the news warehouse.

Output: `analyze/analytics/macro/{date}.json`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common import config
from collect import raw_store

ANALYTICS_DIR = config.ANALYTICS_DIR

POLICY_PAT = re.compile(
    r"\b(fed|federal reserve|rate hike|rate cut|interest rates?|inflation|cpi|"
    r"jobs report|unemployment|payrolls|fomc|treasury yields?|recession)\b",
    re.IGNORECASE,
)


def _series_reading(sid: str) -> dict | None:
    df = raw_store.load_macro_series(sid)
    if df.empty:
        return None
    v = df["value"].astype(float)
    dates = pd.to_datetime(df["date"])
    gaps = dates.diff().dt.days.dropna()
    freq_days = float(gaps.median()) if len(gaps) else None
    n = len(v)
    return {
        "series": sid,
        "date": str(df["date"].iloc[-1]),
        "value": round(float(v.iloc[-1]), 4),
        "change_1p": round(float(v.iloc[-1] - v.iloc[-2]), 4) if n >= 2 else None,
        "change_12p": round(float(v.iloc[-1] - v.iloc[-13]), 4) if n >= 13 else None,
        "frequency_days": freq_days,
        "last_6": [
            {"date": str(df["date"].iloc[i]), "value": round(float(v.iloc[i]), 4)}
            for i in range(max(0, n - 6), n)
        ],
    }


def _upcoming_releases(api_key: str) -> list[dict]:
    """Best-effort: FRED release calendar (next few days)."""
    if not api_key:
        return []
    try:
        import requests

        r = requests.get(
            "https://api.stlouisfed.org/release/current",
            params={"api_key": api_key, "file_type": "json"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for rel in (data.get("releases") or [])[:20]:
            out.append(
                {
                    "name": rel.get("name"),
                    "release_date": rel.get("release_date"),
                    "series": [s.get("id") for s in (rel.get("series") or [])][:10],
                }
            )
        return out
    except Exception:  # noqa: BLE001 — best-effort only
        return []


def build(series_ids: list[str]) -> dict:
    config.load_env()
    api_key = (config.get("FRED_API_KEY") or "").strip()

    readings = [x for x in (_series_reading(s) for s in series_ids) if x]

    policy_news = []
    for slug in raw_store.all_news_feeds():
        for it in raw_store.load_news(slug):
            if POLICY_PAT.search(it.get("title", "")):
                policy_news.append({"title": it.get("title", ""), "link": it.get("link", ""), "ts": it.get("ts")})
    policy_news.sort(key=lambda x: x.get("ts") or 0, reverse=True)

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "series": readings,
        "upcoming_releases": _upcoming_releases(api_key),
        "policy_news": policy_news[:25],
        "data_gaps": [] if api_key else ["FRED_API_KEY not set — release calendar unavailable"],
    }


def write(macro: dict) -> Path:
    d = ANALYTICS_DIR / "macro"
    d.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    p = d / f"{day}.json"
    p.write_text(json.dumps(macro, indent=2), encoding="utf-8")
    return p
