"""Point d'entrée de Jarvis.

    python main.py            -> interface graphique (barre système + fenêtre)
    python main.py --cli      -> mode texte dans le terminal
    python main.py --voice    -> mode vocal avec la bulle à l'écran ("Hey Jarvis" ou clap-clap)
    python main.py --voice --console -> mode vocal dans le terminal, sans bulle
"""
import argparse
import sys

from jarvis.config import DATA_DIR, load_config


def _log_to_file_without_console() -> None:
    """Lancé sans terminal (pythonw, Jarvis.app, ouverture de session) : tout part dans ~/.jarvis/jarvis.log.

    Sous Windows, pythonw n'a aucune sortie : la moindre barre de progression ferait planter Jarvis.
    """
    if sys.stdout is not None and "--background" not in sys.argv:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = open(DATA_DIR / "jarvis.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log


def _safe_console() -> None:
    """Console Windows (cp1252) ou sortie redirigée : un emoji ne doit jamais faire planter Jarvis."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _log_to_file_without_console()
    _safe_console()
    parser = argparse.ArgumentParser(description="Jarvis — assistant personnel local")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cli", action="store_true", help="mode texte")
    group.add_argument("--voice", action="store_true", help="mode vocal")
    parser.add_argument("--console", action="store_true", help="avec --voice : pas de bulle, tout dans le terminal")
    parser.add_argument("--background", action="store_true", help="lancé sans terminal : messages dans ~/.jarvis/jarvis.log")
    parser.add_argument("--config", help="chemin vers un config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.cli:
        from jarvis.ui.cli import run_cli
        return run_cli(cfg)
    if args.voice:
        if not args.console:
            try:
                from jarvis.ui.overlay import run_overlay
            except ImportError:
                print("PySide6 absent : mode vocal dans le terminal.")
            else:
                return run_overlay(cfg)
        from jarvis.voice.loop import run_voice
        return run_voice(cfg)

    from jarvis.ui.gui import run_gui
    return run_gui(cfg)


if __name__ == "__main__":
    sys.exit(main())
