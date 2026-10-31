"""Images : métadonnées + description par le modèle vision local."""
from pathlib import Path

from jarvis.analyzers._common import image_to_b64, look


def analyze(path: Path, question: str | None = None) -> dict:
    from PIL import ExifTags, Image

    img = Image.open(path)
    info = {"dimensions": f"{img.width} x {img.height}", "format": img.format, "mode": img.mode}
    try:
        exif = {ExifTags.TAGS.get(k, k): str(v) for k, v in img.getexif().items()}
        keep = ("DateTime", "Make", "Model", "Software")
        info["exif"] = {k: exif[k] for k in keep if k in exif}
    except Exception:
        pass
    if getattr(img, "is_animated", False):
        img.seek(0)
    info["description"] = look([image_to_b64(img)], question, "une image")
    return info
