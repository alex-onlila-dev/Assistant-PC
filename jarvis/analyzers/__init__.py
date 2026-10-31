"""Aiguillage : chaque type de fichier a son analyseur.

Principe : on convertit tout en texte ou en image, pour que le cerveau puisse comprendre.
"""
from pathlib import Path

import filetype

from jarvis.analyzers import archive, audio, binary, image, office, pdf, text, video

TEXT_EXT = {
    ".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".log", ".env", ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".htm", ".css", ".scss", ".php",
    ".java", ".kt", ".go", ".rs", ".c", ".cpp", ".h", ".cs", ".rb", ".sh", ".bat", ".ps1", ".sql",
    ".dart", ".swift", ".vue", ".svelte", ".srt", ".vtt",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic", ".ico"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma", ".amr"}
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v", ".3gp"}
OFFICE_EXT = {".docx", ".xlsx", ".xlsm", ".pptx"}
ARCHIVE_EXT = {".zip", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z"}

HANDLERS = {
    "texte": text.analyze, "pdf": pdf.analyze, "image": image.analyze, "audio": audio.analyze,
    "video": video.analyze, "office": office.analyze, "archive": archive.analyze, "binaire": binary.analyze,
}


def detect_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    for kind, exts in (("texte", TEXT_EXT), ("image", IMAGE_EXT), ("audio", AUDIO_EXT),
                       ("video", VIDEO_EXT), ("office", OFFICE_EXT), ("archive", ARCHIVE_EXT)):
        if ext in exts:
            return kind
    # Extension inconnue ou trompeuse : on regarde le vrai contenu
    guess = filetype.guess(str(path))
    if guess:
        mime = guess.mime
        if mime == "application/pdf":
            return "pdf"
        for prefix, kind in (("image/", "image"), ("audio/", "audio"), ("video/", "video")):
            if mime.startswith(prefix):
                return kind
        if guess.extension in {e.strip(".") for e in ARCHIVE_EXT}:
            return "archive"
    with open(path, "rb") as f:
        chunk = f.read(4096)
    return "binaire" if b"\x00" in chunk else "texte"


def analyze(path: Path, question: str | None = None) -> dict:
    kind = detect_kind(path)
    try:
        result = HANDLERS[kind](path, question)
    except ImportError as e:
        result = {"erreur": f"Dépendance manquante pour ce type de fichier : {e.name}"}
    return {"fichier": str(path), "type": kind, **result}
