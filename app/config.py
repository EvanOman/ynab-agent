"""Configuration management for persistent state between sessions."""

from __future__ import annotations

import json

from app.models import Config
from app.paths import CONFIG_FILE, ensure_dirs


def load_config() -> Config:
    """Load config from disk, or return defaults."""
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text())
        return Config(**data)
    return Config()


def save_config(config: Config) -> None:
    """Save config to disk."""
    ensure_dirs()
    CONFIG_FILE.write_text(config.model_dump_json(indent=2) + "\n")
