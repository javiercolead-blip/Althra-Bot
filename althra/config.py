"""Loads config/profile.yaml and config/sources.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_profile() -> dict:
    return load_yaml("profile.yaml")


def load_sources() -> list[dict]:
    return [s for s in load_yaml("sources.yaml").get("sources", []) if s.get("enabled", True)]
