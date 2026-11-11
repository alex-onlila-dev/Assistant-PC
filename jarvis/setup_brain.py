"""Enregistre le cerveau choisi pendant l'installation dans ~/.jarvis/config.yaml (utilisé par les installateurs).

    JARVIS_BRAIN=claude JARVIS_API_KEY=sk-ant-… python -m jarvis.setup_brain

Variables : JARVIS_BRAIN (ollama | claude | openai | auto), JARVIS_API_KEY ou JARVIS_API_KEY_FILE,
JARVIS_BASE_URL (service compatible OpenAI), JARVIS_MODEL (nom du modèle, facultatif).
La clé passe par l'environnement ou un fichier, jamais par la ligne de commande : elle n'apparaît pas
dans la liste des processus. Le fichier est effacé dès qu'il est lu.
"""
import os
import sys
from pathlib import Path

from jarvis.config import USER_CONFIG, load_config, save_config

BRAINS = ("ollama", "claude", "openai", "auto")


def apply(cfg: dict, brain: str, api_key: str = "", base_url: str = "", model: str = "") -> dict:
    """Écrit le choix dans la configuration ; un champ laissé vide garde sa valeur actuelle."""
    llm = cfg.setdefault("llm", {})
    llm["provider"] = brain
    if brain == "claude":
        section = llm.setdefault("claude", {})
        values = {"api_key": api_key, "model": model}
    elif brain == "openai":
        section = llm.setdefault("openai", {})
        values = {"api_key": api_key, "base_url": base_url.rstrip("/"), "model": model}
    else:
        section, values = llm, {"model": model}
    section.update({k: v for k, v in values.items() if v})
    return cfg


def _key() -> str:
    path = os.environ.get("JARVIS_API_KEY_FILE", "")
    if path and Path(path).is_file():
        key = Path(path).read_text(encoding="utf-8-sig").strip()
        Path(path).unlink(missing_ok=True)
        return key
    return os.environ.get("JARVIS_API_KEY", "").strip()


def main() -> int:
    brain = os.environ.get("JARVIS_BRAIN", "").strip().lower()
    if brain not in BRAINS:
        print(f"JARVIS_BRAIN doit valoir : {', '.join(BRAINS)}")
        return 2
    key = _key()
    cfg = apply(load_config(), brain, key, os.environ.get("JARVIS_BASE_URL", "").strip(),
                os.environ.get("JARVIS_MODEL", "").strip())
    save_config(cfg)
    names = {"ollama": "Ollama (local)", "claude": "Claude", "openai": "service compatible OpenAI",
             "auto": "automatique"}
    print(f"cerveau : {names[brain]}" + (" — clé enregistrée" if key else "") + f" ({USER_CONFIG})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
