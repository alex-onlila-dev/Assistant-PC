"""PDF : texte extrait ; si le PDF est scanné (pas de texte), on regarde les pages en image."""
from pathlib import Path

from jarvis.analyzers._common import clip, image_to_b64, look


def analyze(path: Path, question: str | None = None) -> dict:
    import fitz  # PyMuPDF
    from PIL import Image

    doc = fitz.open(path)
    text = "\n".join(f"--- Page {i + 1} ---\n{page.get_text()}" for i, page in enumerate(doc))
    result = {"pages": doc.page_count, "metadonnees": {k: v for k, v in doc.metadata.items() if v}}

    if len(text.strip()) > 50 * max(doc.page_count, 1) or doc.page_count == 0:
        result["contenu"] = clip(text)
    else:
        images = []
        for page in list(doc)[:3]:
            pix = page.get_pixmap(dpi=110)
            images.append(image_to_b64(Image.frombytes("RGB", (pix.width, pix.height), pix.samples)))
        result["note"] = "PDF scanné : analyse visuelle des 3 premières pages."
        result["description_visuelle"] = look(images, question, "les pages d'un document PDF scanné")
    doc.close()
    return result
