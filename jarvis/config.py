"""Chargement de la configuration.

Ordre de recherche : chemin donné en argument, sinon ~/.jarvis/config.yaml (la config de l'utilisateur,
conservée lors des mises à jour), sinon le config.yaml livré avec Jarvis.
JARVIS_HOME permet de changer le dossier ~/.jarvis (tests, plusieurs profils).
"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JARVIS_HOME") or Path.home() / ".jarvis")
DEFAULT_CONFIG = ROOT / "config.yaml"
USER_CONFIG = DATA_DIR / "config.yaml"


def load_config(path: str | None = None) -> dict:
    if path:
        cfg_path = Path(path)
    else:
        cfg_path = USER_CONFIG if USER_CONFIG.exists() else DEFAULT_CONFIG
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.setdefault("data_dir", str(DATA_DIR))
    return cfg
