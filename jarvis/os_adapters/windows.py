"""Adaptateur Windows 10/11."""
import os
import subprocess
from pathlib import Path

from jarvis.os_adapters.base import OSAdapter


class WindowsAdapter(OSAdapter):
    name = "Windows"
    SETTINGS = {
        "accueil": "ms-settings:",
        "affichage": "ms-settings:display",
        "son": "ms-settings:sound",
        "bluetooth": "ms-settings:bluetooth",
        "wifi": "ms-settings:network-wifi",
        "réseau": "ms-settings:network",
        "notifications": "ms-settings:notifications",
        "alimentation": "ms-settings:powersleep",
        "batterie": "ms-settings:batterysaver",
        "date et heure": "ms-settings:dateandtime",
        "langue": "ms-settings:regionlanguage",
        "personnalisation": "ms-settings:personalization",
        "fond d'écran": "ms-settings:personalization-background",
        "applications": "ms-settings:appsfeatures",
        "confidentialité": "ms-settings:privacy",
        "mises à jour": "ms-settings:windowsupdate",
        "stockage": "ms-settings:storagesense",
        "souris": "ms-settings:mousetouchpad",
        "clavier": "ms-settings:typing",
        "imprimantes": "ms-settings:printers",
        "comptes": "ms-settings:yourinfo",
    }

    def open_file(self, path: Path) -> None:
        os.startfile(str(path))  # type: ignore[attr-defined]

    def reveal(self, path: Path) -> None:
        subprocess.Popen(["explorer", "/select,", str(path)])

    def list_apps(self) -> dict[str, str]:
        roots = [
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        apps: dict[str, str] = {}
        for root in roots:
            if root.exists():
                for p in root.rglob("*"):
                    if p.suffix.lower() in (".lnk", ".url", ".appref-ms"):
                        apps.setdefault(p.stem, str(p))
        # Applications intégrées utiles
        apps.setdefault("Explorateur de fichiers", "explorer.exe")
        apps.setdefault("Bloc-notes", "notepad.exe")
        apps.setdefault("Calculatrice", "calc.exe")
        apps.setdefault("Invite de commandes", "cmd.exe")
        apps.setdefault("Gestionnaire des tâches", "taskmgr.exe")
        apps.setdefault("Horloge", "ms-clock:")
        return apps

    def launch(self, target: str) -> None:
        os.startfile(target)  # type: ignore[attr-defined]

    def open_settings(self, section: str) -> None:
        uri = self.SETTINGS.get(section.lower(), "ms-settings:")
        os.startfile(uri)  # type: ignore[attr-defined]
