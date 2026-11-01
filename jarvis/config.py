"""Chargement de la configuration.

Ordre de recherche : chemin donné en argument, sinon ~/.jarvis/config.yaml (la config de l'utilisateur,
conservée lors des mises à jour) complétée par le config.yaml livré avec Jarvis pour les réglages qu'elle
n'a pas encore (nouveaux réglages d'une mise à jour).
JARVIS_HOME permet de changer le dossier ~/.jarvis (tests, plusieurs profils).
"""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JARVIS_HOME") or Path.home() / ".jarvis")
DEFAULT_CONFIG = ROOT / "config.yaml"
USER_CONFIG = DATA_DIR / "config.yaml"


def _read(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def load_config(path: str | None = None) -> dict:
    if path:
        cfg = _read(Path(path))
    elif USER_CONFIG.exists():
        cfg = _merge(_read(DEFAULT_CONFIG), _read(USER_CONFIG))
    else:
        cfg = _read(DEFAULT_CONFIG)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.setdefault("data_dir", str(DATA_DIR))
    return cfg


def save_config(cfg: dict) -> Path:
    """Enregistre la configuration de l'utilisateur (fenêtre Paramètres). La précédente est gardée en .bak."""
    data = {k: v for k, v in cfg.items() if k != "data_dir"}
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if USER_CONFIG.exists():
        USER_CONFIG.replace(USER_CONFIG.with_suffix(".yaml.bak"))
    text = ("# Configuration de Jarvis, enregistrée par la fenêtre Paramètres.\n"
            f"# Explication de chaque réglage : {DEFAULT_CONFIG}\n\n"
            + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False))
    tmp = USER_CONFIG.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(USER_CONFIG)
    return USER_CONFIG
