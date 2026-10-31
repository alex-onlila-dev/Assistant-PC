"""Résolution des chemins et protection des dossiers système."""
from pathlib import Path

from jarvis.core.context import ctx


def resolve(path: str) -> Path:
    """Chemin absolu. Un chemin relatif part du dossier personnel, pas du dossier de lancement."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.home() / p
    return p.resolve()


def shown(path: str) -> str:
    """Chemin tel qu'il sera réellement utilisé, pour l'afficher dans une confirmation."""
    try:
        return str(resolve(path))
    except (OSError, RuntimeError):
        return str(path)


def preview(text: str, limit: int = 300) -> str:
    """Aperçu du contenu à écrire, montré dans la confirmation."""
    text = str(text or "")
    if not text:
        return "(vide)"
    return text if len(text) <= limit else text[:limit] + f"… (+{len(text) - limit} caractères)"


def ensure_writable(p: Path) -> None:
    """Refuse toute écriture/suppression dans un dossier protégé."""
    protected = ctx.cfg.get("security", {}).get("protected_paths", [])
    for prot in protected:
        try:
            base = Path(prot).expanduser().resolve()
        except OSError:
            continue
        if p == base or base in p.parents:
            raise PermissionError(f"Dossier protégé, action refusée : {base}")


def human_size(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} Po"
