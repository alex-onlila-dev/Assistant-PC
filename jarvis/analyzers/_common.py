"""Outils partagés par les analyseurs."""
import base64
import io

from jarvis.core.context import ctx


def max_chars() -> int:
    return ctx.cfg.get("analysis", {}).get("max_chars", 20000)


def clip(text: str, limit: int | None = None) -> str:
    limit = limit or max_chars()
    return text if len(text) <= limit else text[:limit] + "\n… [tronqué]"


def image_to_b64(img) -> str:
    """Redimensionne une image PIL et la convertit en base64 (JPEG)."""
    side = ctx.cfg.get("analysis", {}).get("image_max_side", 1024)
    img = img.convert("RGB")
    img.thumbnail((side, side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def look(images_b64: list[str], question: str | None, what: str) -> str:
    """Demande au modèle vision local de décrire des images."""
    prompt = (f"Voici {what}. Décris précisément ce que tu vois en français : éléments, texte visible, "
              f"personnes, lieux, ambiance.")
    if question:
        prompt += f" Réponds aussi à cette question : {question}"
    try:
        return ctx.llm.describe_images(images_b64, prompt)
    except Exception as e:
        return f"(Vision indisponible : {e})"
