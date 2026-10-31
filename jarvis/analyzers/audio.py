"""Audio : transcription locale avec Whisper."""
from pathlib import Path

from jarvis.analyzers._common import clip
from jarvis.core.context import ctx


def analyze(path: Path, question: str | None = None) -> dict:
    from jarvis.voice.stt import get_transcriber

    text, info = get_transcriber(ctx.cfg).transcribe_file(str(path))
    return {
        "duree_secondes": round(info.get("duration", 0), 1),
        "langue_detectee": info.get("language"),
        "transcription": clip(text) if text.strip() else "(aucune parole détectée : musique ou silence)",
    }
