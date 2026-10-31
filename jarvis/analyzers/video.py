"""Vidéo : images clés (vision) + bande son (Whisper), via ffmpeg."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from jarvis.analyzers._common import clip, image_to_b64, look
from jarvis.core.context import ctx


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",
                          "-show_streams", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def analyze(path: Path, question: str | None = None) -> dict:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return {"erreur": "ffmpeg n'est pas installé : impossible d'analyser la vidéo."}
    from PIL import Image

    meta = _probe(path)
    duration = float(meta.get("format", {}).get("duration", 0) or 0)
    vstream = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})
    has_audio = any(s.get("codec_type") == "audio" for s in meta.get("streams", []))
    n_frames = ctx.cfg.get("analysis", {}).get("video_frames", 6)
    result = {"duree_secondes": round(duration, 1),
              "resolution": f"{vstream.get('width')} x {vstream.get('height')}" if vstream else None}

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        # Images clés réparties sur toute la vidéo
        images = []
        for i in range(n_frames):
            t = duration * (i + 0.5) / n_frames if duration else 0
            frame = tmpdir / f"f{i}.jpg"
            subprocess.run(["ffmpeg", "-v", "quiet", "-ss", f"{t:.2f}", "-i", str(path),
                            "-frames:v", "1", "-y", str(frame)], check=False)
            if frame.exists():
                images.append(image_to_b64(Image.open(frame)))
        if images:
            result["description_visuelle"] = look(
                images, question, f"{len(images)} images extraites dans l'ordre d'une vidéo de {duration:.0f} s")

        # Bande son
        if has_audio:
            wav = tmpdir / "audio.wav"
            subprocess.run(["ffmpeg", "-v", "quiet", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
                            "-y", str(wav)], check=False)
            if wav.exists():
                from jarvis.voice.stt import get_transcriber
                text, _ = get_transcriber(ctx.cfg).transcribe_file(str(wav))
                result["transcription"] = clip(text) if text.strip() else "(pas de parole détectée)"
        else:
            result["transcription"] = "(vidéo sans son)"
    return result
