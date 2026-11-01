"""Lancement automatique de Jarvis (mode vocal) à l'ouverture de session, réglable depuis les Paramètres.

On réutilise ce que l'installateur a créé : l'entrée du menu des applications (Linux), Jarvis.app (macOS),
le raccourci du menu Démarrer (Windows). Sans installation, le réglage n'est pas disponible.
"""
import os
import shutil
import sys
from pathlib import Path

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.jarvis.assistant</string>
  <key>ProgramArguments</key><array><string>/usr/bin/open</string><string>-a</string><string>{app}</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
"""


def _paths() -> tuple[Path, Path]:
    """(ce que l'installateur a créé, fichier qui lance Jarvis à l'ouverture de session)"""
    home = Path.home()
    if sys.platform.startswith("win"):
        programs = Path(os.environ.get("APPDATA") or home / "AppData/Roaming") / "Microsoft/Windows/Start Menu/Programs"
        return programs / "Jarvis.lnk", programs / "Startup/Jarvis.lnk"
    if sys.platform == "darwin":
        app = Path(os.environ.get("JARVIS_MAC_APP") or home / "Applications/Jarvis.app")
        return app, home / "Library/LaunchAgents/local.jarvis.assistant.plist"
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return data / "applications/jarvis.desktop", config / "autostart/jarvis.desktop"


def available() -> bool:
    return _paths()[0].exists()


def enabled() -> bool:
    return _paths()[1].exists()


def set_enabled(on: bool) -> None:
    source, target = _paths()
    if not on:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        target.write_text(PLIST.format(app=source), encoding="utf-8")
    else:
        shutil.copyfile(source, target)
