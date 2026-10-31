"""Adaptateur macOS (Ventura et plus récent)."""
import subprocess
from pathlib import Path

from jarvis.os_adapters.base import OSAdapter

_PANE = "x-apple.systempreferences:"


class MacAdapter(OSAdapter):
    name = "macOS"
    SETTINGS = {
        "accueil": "",
        "affichage": "com.apple.Displays-Settings.extension",
        "son": "com.apple.Sound-Settings.extension",
        "bluetooth": "com.apple.BluetoothSettings",
        "wifi": "com.apple.wifi-settings-extension",
        "réseau": "com.apple.Network-Settings.extension",
        "notifications": "com.apple.Notifications-Settings.extension",
        "alimentation": "com.apple.Battery-Settings.extension",
        "batterie": "com.apple.Battery-Settings.extension",
        "date et heure": "com.apple.Date-Time-Settings.extension",
        "langue": "com.apple.Localization-Settings.extension",
        "fond d'écran": "com.apple.Wallpaper-Settings.extension",
        "confidentialité": "com.apple.settings.PrivacySecurity.extension",
        "mises à jour": "com.apple.Software-Update-Settings.extension",
        "stockage": "com.apple.settings.Storage",
        "clavier": "com.apple.Keyboard-Settings.extension",
        "souris": "com.apple.Mouse-Settings.extension",
        "imprimantes": "com.apple.Print-Scan-Settings.extension",
    }

    def open_file(self, path: Path) -> None:
        subprocess.Popen(["open", str(path)])

    def reveal(self, path: Path) -> None:
        subprocess.Popen(["open", "-R", str(path)])

    def list_apps(self) -> dict[str, str]:
        apps: dict[str, str] = {}
        for root in (Path("/Applications"), Path("/System/Applications"),
                     Path("/System/Applications/Utilities"), Path.home() / "Applications"):
            if root.exists():
                for p in root.glob("*.app"):
                    apps.setdefault(p.stem, str(p))
        return apps

    def launch(self, target: str) -> None:
        subprocess.Popen(["open", target])

    def open_settings(self, section: str) -> None:
        pane = self.SETTINGS.get(section.lower(), "")
        if pane:
            subprocess.Popen(["open", f"{_PANE}{pane}"])
        else:
            subprocess.Popen(["open", "-a", "System Settings"])

    def notify(self, title: str, message: str) -> None:
        safe = lambda s: s.replace('"', "'")  # noqa: E731
        subprocess.run(["osascript", "-e",
                        f'display notification "{safe(message)}" with title "{safe(title)}"'], check=False)
