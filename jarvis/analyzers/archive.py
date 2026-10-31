"""Archives : liste du contenu (sans rien extraire sur le disque)."""
import tarfile
import zipfile
from pathlib import Path

from jarvis.tools._paths import human_size

MAX_ENTRIES = 200


def analyze(path: Path, question: str | None = None) -> dict:
    entries: list[str] = []
    total = 0
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            total = len(infos)
            entries = [f"{i.filename} ({human_size(i.file_size)})" for i in infos[:MAX_ENTRIES]]
    elif tarfile.is_tarfile(path):
        with tarfile.open(path) as t:
            members = t.getmembers()
            total = len(members)
            entries = [f"{m.name} ({human_size(m.size)})" for m in members[:MAX_ENTRIES]]
    elif path.suffix.lower() == ".rar":
        import rarfile
        with rarfile.RarFile(path) as r:
            infos = r.infolist()
            total = len(infos)
            entries = [f"{i.filename} ({human_size(i.file_size)})" for i in infos[:MAX_ENTRIES]]
    else:
        return {"erreur": "Format d'archive non pris en charge (7z : à ajouter avec py7zr)."}
    return {"nombre_elements": total, "contenu": entries,
            "note": "Pour analyser un fichier interne, il faut d'abord extraire l'archive."}
