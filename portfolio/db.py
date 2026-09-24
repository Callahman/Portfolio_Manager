"""Simulated portfolio — SQLite schema (Step 6).

Tables:
  positions(ticker, shares, avg_cost)   current holdings
  cash(value)                           single row
  trades(id, ts, ticker, side, shares, price, cost_bps, tx_cost, rationale)
  marks(date, total, cash, positions_value, benchmark_close, benchmark_total)
  decisions(id, ts, recommendation_json, outcome_note)

The paper portfolio lives at portfolio/portfolio.db (gitignored).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from common import config

DB_PATH = config.PORTFOLIO_DIR / "portfolio.db"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    p = db_path or DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS positions (
            ticker TEXT PRIMARY KEY,
            shares REAL NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cash (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            value REAL NOT NULL DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            shares REAL NOT NULL,
            price REAL NOT NULL,
            cost_bps REAL NOT NULL DEFAULT 0,
            tx_cost REAL NOT NULL DEFAULT 0,
            rationale TEXT DEFAULT ''
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS marks (
            date TEXT PRIMARY KEY,
            total REAL NOT NULL,
            cash REAL NOT NULL,
            positions_value REAL NOT NULL,
            benchmark_close REAL,
            benchmark_total REAL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            recommendation_json TEXT NOT NULL,
            outcome_note TEXT DEFAULT ''
        )"""
    )
    conn.commit()
    return conn


def is_seeded(db_path: Path | None = None) -> bool:
    p = db_path or DB_PATH
    if not p.exists():
        return False
    conn = sqlite3.connect(p)
    try:
        row = conn.execute("SELECT COUNT(*) FROM cash").fetchone()
        return bool(row and row[0] > 0)
    finally:
        conn.close()


def seed(start_balance: float, start_positions: list[tuple[str, float]] | None = None,
         db_path: Path | None = None) -> None:
    """Seed from .env: starting balance + optional starting positions."""
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM cash WHERE id = 1")
        conn.execute("INSERT INTO cash (id, value) VALUES (1, ?)", (float(start_balance),))
        for ticker, shares in (start_positions or []):
            conn.execute(
                "INSERT OR REPLACE INTO positions (ticker, shares, avg_cost) VALUES (?,?,?)",
                (ticker, float(shares), 0.0),
            )
        conn.commit()
    finally:
        conn.close()