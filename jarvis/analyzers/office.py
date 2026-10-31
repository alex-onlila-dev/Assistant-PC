"""Word, Excel, PowerPoint : extraction du contenu."""
from pathlib import Path

from jarvis.analyzers._common import clip


def _docx(path: Path) -> dict:
    from docx import Document

    doc = Document(path)
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for t_i, table in enumerate(doc.tables, 1):
        parts.append(f"[Tableau {t_i}]")
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return {"paragraphes": len(doc.paragraphs), "tableaux": len(doc.tables), "contenu": clip("\n".join(parts))}


def _xlsx(path: Path) -> dict:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    out, sheets = [], {}
    for ws in wb.worksheets:
        sheets[ws.title] = f"{ws.max_row} lignes x {ws.max_column} colonnes"
        out.append(f"=== Feuille : {ws.title} ===")
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= 200:
                out.append("… [lignes suivantes non affichées]")
                break
            if any(v is not None for v in row):
                out.append(" | ".join("" if v is None else str(v) for v in row))
    wb.close()
    return {"feuilles": sheets, "contenu": clip("\n".join(out))}


def _pptx(path: Path) -> dict:
    from pptx import Presentation

    prs = Presentation(path)
    out = []
    for i, slide in enumerate(prs.slides, 1):
        out.append(f"--- Diapositive {i} ---")
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                out.append(shape.text_frame.text)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            out.append(f"[Notes] {slide.notes_slide.notes_text_frame.text}")
    return {"diapositives": len(prs.slides), "contenu": clip("\n".join(out))}


def analyze(path: Path, question: str | None = None) -> dict:
    ext = path.suffix.lower()
    if ext == ".docx":
        return _docx(path)
    if ext in (".xlsx", ".xlsm"):
        return _xlsx(path)
    if ext == ".pptx":
        return _pptx(path)
    return {"erreur": f"Format Office non pris en charge : {ext}"}
