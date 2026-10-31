"""Adaptateur Linux (GNOME, KDE et autres environnements freedesktop)."""
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from jarvis.os_adapters.base import OSAdapter

GNOME_PANELS = {
    "accueil": "", "affichage": "display", "son": "sound", "bluetooth": "bluetooth",
    "wifi": "wifi", "réseau": "network", "notifications": "notifications",
    "alimentation": "power", "batterie": "power", "date et heure": "datetime",
    "langue": "region", "fond d'écran": "background", "confidentialité": "privacy",
    "applications": "applications", "clavier": "keyboard", "souris": "mouse",
    "imprimantes": "printers", "comptes": "user-accounts",
}


class LinuxAdapter(OSAdapter):
    name = "Linux"
    SETTINGS = GNOME_PANELS

    @property
    def desktop(self) -> str:
        return os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    def open_file(self, path: Path) -> None:
        subprocess.Popen(["xdg-open", str(path)], start_new_session=True)

    def reveal(self, path: Path) -> None:
        if shutil.which("nautilus"):
            subprocess.Popen(["nautilus", "--select", str(path)], start_new_session=True)
        else:
            subprocess.Popen(["xdg-open", str(path.parent)], start_new_session=True)

    def list_apps(self) -> dict[str, str]:
        dirs = [Path("/usr/share/applications"), Path("/usr/local/share/applications"),
                Path.home() / ".local/share/applications",
                Path("/var/lib/flatpak/exports/share/applications")]
        apps: dict[str, str] = {}
        for d in dirs:
            if not d.exists():
                continue
            for f in d.glob("*.desktop"):
                name, hidden = None, False
                try:
                    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if line.startswith("Name=") and name is None:
                            name = line[5:].strip()
                        elif line.strip() in ("NoDisplay=true", "Hidden=true"):
                            hidden = True
                except OSError:
                    continue
                if name and not hidden:
                    apps.setdefault(name, str(f))
        return apps

    def launch(self, target: str) -> None:
        desktop_file = Path(target)
        if shutil.which("gtk-launch"):
            subprocess.Popen(["gtk-launch", desktop_file.stem], start_new_session=True)
            return
        # Repli : lire la ligne Exec= du fichier .desktop
        for line in desktop_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("Exec="):
                cmd = [a for a in shlex.split(line[5:]) if not a.startswith("%")]
                subprocess.Popen(cmd, start_new_session=True)
                return
        raise RuntimeError(f"Impossible de lancer {target}")

    def open_settings(self, section: str) -> None:
        if "kde" in self.desktop and shutil.which("systemsettings"):
            subprocess.Popen(["systemsettings"], start_new_session=True)
            return
        if shutil.which("gnome-control-center"):
            panel = self.SETTINGS.get(section.lower(), "")
            subprocess.Popen(["gnome-control-center", *([panel] if panel else [])], start_new_session=True)
            return
        raise RuntimeError("Aucun gestionnaire de paramètres reconnu sur ce bureau.")

    def notify(self, title: str, message: str) -> None:
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", title, message], check=False)
        else:
            super().notify(title, message)
