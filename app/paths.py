"""Central path definitions — all data lives under ~/.config/ynab-agent/."""

from __future__ import annotations

from pathlib import Path

DATA_DIR = Path.home() / ".config" / "ynab-agent"
ENV_FILE = DATA_DIR / ".env"
CONFIG_FILE = DATA_DIR / "config.json"
HISTORY_DIR = DATA_DIR / "history"
DECISIONS_FILE = HISTORY_DIR / "decisions.jsonl"
REBALANCES_FILE = HISTORY_DIR / "rebalances.jsonl"


def ensure_dirs() -> None:
    """Create data directories if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
