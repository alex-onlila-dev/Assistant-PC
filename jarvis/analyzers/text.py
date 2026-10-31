"""Texte et code : lecture directe."""
from pathlib import Path

from jarvis.analyzers._common import clip


def analyze(path: Path, question: str | None = None) -> dict:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return {
        "encodage": enc,
        "lignes": content.count("\n") + 1,
        "caracteres": len(content),
        "contenu": clip(content),
    }
