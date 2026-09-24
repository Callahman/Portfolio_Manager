"""Configuration loading + canonical repository paths.

Every package loads the repo-root `.env` (python-dotenv). The canonical
storage paths here keep the segregated packages (collect/ -> validate/ ->
analyze/) in agreement about where their schemas live.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- canonical storage paths (segregated schemas) ---
RAW_DIR = REPO_ROOT / "collect" / "raw"          # warehouse/raw
VALIDATED_DIR = REPO_ROOT / "validate" / "validated"  # warehouse/validated
ANALYTICS_DIR = REPO_ROOT / "analyze" / "analytics"   # warehouse/analytics
PORTFOLIO_DIR = REPO_ROOT / "portfolio"
HISTORY_DIR = REPO_ROOT / "history"
ARCHIVES_DIR = REPO_ROOT / "archives"
REPORTS_DIR = REPO_ROOT / "reports"

# alias used in the outline's pipeline diagrams
WAREHOUSE_RAW = RAW_DIR


def load_env() -> dict:
    """Load the repo-root .env into os.environ (idempotent)."""
    load_dotenv(REPO_ROOT / ".env")
    return dict(os.environ)


def get(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def get_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default) or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default
