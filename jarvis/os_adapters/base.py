"""Interface commune à tous les systèmes d'exploitation.

Pour ajouter un OS : créer une classe qui hérite d'OSAdapter et implémente les méthodes abstraites.
"""
import difflib
import webbrowser
from abc import ABC, abstractmethod
from pathlib import Path


class OSAdapter(ABC):
    name = "inconnu"
    # Sections de paramètres communes -> identifiant propre à l'OS
    SETTINGS: dict[str, str] = {}

    # --- Fichiers ---
    @abstractmethod
    def open_file(self, path: Path) -> None:
        """Ouvre un fichier avec l'application par défaut du système."""

    @abstractmethod
    def reveal(self, path: Path) -> None:
        """Affiche le fichier dans l'explorateur / Finder / gestionnaire de fichiers."""

    # --- Applications ---
    @abstractmethod
    def list_apps(self) -> dict[str, str]:
        """{nom affiché: identifiant de lancement}"""

    @abstractmethod
    def launch(self, target: str) -> None:
        """Lance une application à partir de son identifiant."""

    def open_app(self, name: str) -> str:
        apps = self.list_apps()
        key = self.find_app(name, apps)
        if key is None:
            raise FileNotFoundError(f"Application introuvable : {name}")
        self.launch(apps[key])
        return key

    @staticmethod
    def find_app(name: str, apps: dict[str, str]) -> str | None:
        low = {k.lower(): k for k in apps}
        n = name.lower().strip()
        if n in low:
            return low[n]
        contains = [k for lk, k in low.items() if n in lk]
        if contains:
            return min(contains, key=len)
        close = difflib.get_close_matches(n, list(low), n=1, cutoff=0.6)
        return low[close[0]] if close else None

    # --- Paramètres ---
    @abstractmethod
    def open_settings(self, section: str) -> None:
        """Ouvre une section des paramètres système."""

    def settings_sections(self) -> list[str]:
        return list(self.SETTINGS)

    # --- Divers ---
    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def notify(self, title: str, message: str) -> None:
        try:
            from plyer import notification
            notification.notify(title=title, message=message, app_name="Jarvis", timeout=10)
        except Exception:
            print(f"[{title}] {message}")
