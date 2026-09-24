"""warehouse/raw — raw fetch storage (its own schema, per Appendix A).

Layout:
  collect/raw/
    prices/{TICKER}.parquet   rolling daily OHLCV series (upsert per fetch)
    macro/{SERIES_ID}.parquet FRED observations (date, value)
    news/{FEED_SLUG}.jsonl    news items (dedup by link, newest wins)
    meta.db                   SQLite fetch metadata (source, fetched_at, rows, status)

The rolling series are idempotent upserts: a re-fetch of the same data
changes nothing; a fetch that finds new rows extends the series.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pandas as pd

from common import config

RAW_DIR = config.RAW_DIR
META_DB = RAW_DIR / "meta.db"

PRICE_COLS = ["date", "open", "high", "low", "close", "volume"]
MACRO_COLS = ["date", "value"]


def _ensure_dirs() -> None:
    for sub in ("prices", "macro", "news"):
        (RAW_DIR / sub).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- prices ---

def upsert_price_series(ticker: str, df: pd.DataFrame) -> int:
    """Merge a daily OHLCV frame into the rolling series. Returns new rows."""
    _ensure_dirs()
    if df is None or df.empty:
        return 0
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for c in ("open", "high", "low", "close", "volume"):
        if c not in df.columns:
            df[c] = pd.NA
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[[c for c in PRICE_COLS if c in df.columns]]
    path = RAW_DIR / "prices" / f"{ticker}.parquet"
    if path.exists():
        old = pd.read_parquet(path)
        merged = pd.concat([old, df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["date"], keep="last")
        new_count = int(merged["date"].nunique() - old["date"].nunique())
    else:
        merged = df
        new_count = int(len(merged))
    merged = merged.sort_values("date").reset_index(drop=True)
    merged.to_parquet(path, index=False)
    return new_count


def load_price_series(ticker: str) -> pd.DataFrame:
    path = RAW_DIR / "prices" / f"{ticker}.parquet"
    if not path.exists():
        return pd.DataFrame(columns=PRICE_COLS)
    return pd.read_parquet(path)


def all_price_tickers() -> list[str]:
    d = RAW_DIR / "prices"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.parquet"))


# ----------------------------------------------------------------- macro ---

def upsert_macro_series(series_id: str, df: pd.DataFrame) -> int:
    _ensure_dirs()
    if df is None or df.empty:
        return 0
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    df = df[MACRO_COLS]
    path = RAW_DIR / "macro" / f"{series_id}.parquet"
    if path.exists():
        old = pd.read_parquet(path)
        merged = pd.concat([old, df], ignore_index=True)
        merged = merged.drop_duplicates(subset=["date"], keep="last")
        new_count = int(merged["date"].nunique() - old["date"].nunique())
    else:
        merged = df
        new_count = int(len(merged))
    merged = merged.sort_values("date").reset_index(drop=True)
    merged.to_parquet(path, index=False)
    return new_count


def load_macro_series(series_id: str) -> pd.DataFrame:
    path = RAW_DIR / "macro" / f"{series_id}.parquet"
    if not path.exists():
        return pd.DataFrame(columns=MACRO_COLS)
    return pd.read_parquet(path)


def all_macro_series_ids() -> list[str]:
    d = RAW_DIR / "macro"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.parquet"))


# ------------------------------------------------------------------ news ---

def append_news(feed_slug: str, items: list[dict]) -> int:
    """Append news items, dedup by link (newest wins). Returns new items."""
    _ensure_dirs()
    if not items:
        return 0
    path = RAW_DIR / "news" / f"{feed_slug}.jsonl"
    existing: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                it = json.loads(line)
                existing[it.get("link", it.get("title", ""))] = it
            except json.JSONDecodeError:
                continue
    before = len(existing)
    for it in items:
        key = it.get("link") or it.get("title", "")
        prev = existing.get(key)
        if prev is None or (it.get("ts") or 0) >= (prev.get("ts") or 0):
            existing[key] = it
    with path.open("w", encoding="utf-8") as f:
        for it in sorted(existing.values(), key=lambda x: x.get("ts") or 0, reverse=True):
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return len(existing) - before


def load_news(feed_slug: str) -> list[dict]:
    path = RAW_DIR / "news" / f"{feed_slug}.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def all_news_feeds() -> list[str]:
    d = RAW_DIR / "news"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.jsonl"))


# ------------------------------------------------------------- fetch meta ---

def _connect() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(META_DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fetches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            kind TEXT NOT NULL,
            fetched_at REAL NOT NULL,
            rows INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT DEFAULT ''
        )"""
    )
    return conn


def record_fetch(source: str, kind: str, rows: int, status: str, error: str = "") -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO fetches (source, kind, fetched_at, rows, status, error) VALUES (?,?,?,?,?,?)",
            (source, kind, time.time(), int(rows), status, error[:2000]),
        )
        conn.commit()
    finally:
        conn.close()


def recent_fetches(hours: float | None = None) -> list[dict]:
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT source, kind, fetched_at, rows, status, error FROM fetches ORDER BY fetched_at DESC LIMIT 500"
        )
        rows = [
            {
                "source": r[0],
                "kind": r[1],
                "fetched_at": r[2],
                "rows": r[3],
                "status": r[4],
                "error": r[5],
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()
    if hours is not None:
        cutoff = time.time() - hours * 3600
        rows = [r for r in rows if r["fetched_at"] >= cutoff]
    return rows
