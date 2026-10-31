"""Chargement de la configuration."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path.home() / ".jarvis"


def load_config(path: str | None = None) -> dict:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.setdefault("data_dir", str(DATA_DIR))
    return cfg
