"""Fichiers inconnus ou binaires : métadonnées et signature."""
from datetime import datetime
from pathlib import Path

import filetype

from jarvis.tools._paths import human_size


def analyze(path: Path, question: str | None = None) -> dict:
    st = path.stat()
    guess = filetype.guess(str(path))
    with open(path, "rb") as f:
        head = f.read(16)
    return {
        "taille": human_size(st.st_size),
        "type_reel": guess.mime if guess else "inconnu",
        "extension_reelle": guess.extension if guess else None,
        "signature_hex": head.hex(" "),
        "modifie": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "note": "Contenu binaire non lisible directement. Il peut être ouvert avec open_file.",
    }
