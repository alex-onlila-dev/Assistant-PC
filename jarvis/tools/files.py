"""CRUD sur les fichiers.

Lecture  : sans confirmation.
Écriture, déplacement, suppression, ouverture : confirmation obligatoire.
"""
import fnmatch
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from send2trash import send2trash

from jarvis.core.context import ctx
from jarvis.core.tools import param, registry
from jarvis.tools._paths import ensure_writable, human_size, preview, resolve, shown


def _is_text(p: Path) -> bool:
    with open(p, "rb") as f:
        chunk = f.read(4096)
    return b"\x00" not in chunk


def _read_text(p: Path, max_chars: int) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            text = p.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    return text if len(text) <= max_chars else text[:max_chars] + "\n… [tronqué]"


# ---------------------------------------------------------------- LECTURE
@registry.register(
    "read_file", "Lit le contenu d'un fichier texte (code, txt, md, json, csv…).",
    {"path": param("string", "Chemin du fichier")}, ["path"])
def read_file(path: str) -> dict:
    p = resolve(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    if not _is_text(p):
        return {"info": "Fichier non textuel : utilise analyze_file pour l'analyser.", "chemin": str(p)}
    max_chars = ctx.cfg.get("analysis", {}).get("max_chars", 20000)
    return {"chemin": str(p), "contenu": _read_text(p, max_chars)}


@registry.register(
    "list_directory", "Liste le contenu d'un dossier.",
    {"path": param("string", "Chemin du dossier (défaut : dossier personnel)"),
     "show_hidden": param("boolean", "Afficher les fichiers cachés")})
def list_directory(path: str = "~", show_hidden: bool = False) -> dict:
    p = resolve(path)
    if not p.is_dir():
        raise NotADirectoryError(str(p))
    entries = []
    for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        if not show_hidden and e.name.startswith("."):
            continue
        try:
            st = e.stat()
        except OSError:
            continue
        entries.append({"nom": e.name, "type": "dossier" if e.is_dir() else "fichier",
                        "taille": human_size(st.st_size) if e.is_file() else "",
                        "modifié": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")})
        if len(entries) >= 300:
            break
    return {"dossier": str(p), "elements": entries, "total_affiché": len(entries)}


@registry.register(
    "search_files",
    "Cherche des fichiers ou dossiers par nom (sous-chaîne ou motif comme *.pdf).",
    {"query": param("string", "Nom ou motif à chercher, ex: 'rapport' ou '*.mp4'"),
     "root": param("string", "Dossier de départ (défaut : dossier personnel)"),
     "extensions": param("array", "Extensions à garder, ex: ['.pdf', '.docx']", items={"type": "string"})},
    ["query"])
def search_files(query: str, root: str = "~", extensions: list[str] | None = None) -> dict:
    s = ctx.cfg.get("search", {})
    skip = set(s.get("skip_dirs", []))
    max_results = s.get("max_results", 50)
    deadline = time.monotonic() + s.get("timeout_seconds", 20)
    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in (extensions or [])}
    q = query.lower()
    is_glob = any(c in q for c in "*?[")
    results, timed_out = [], False

    for dirpath, dirnames, filenames in os.walk(resolve(root)):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        if time.monotonic() > deadline:
            timed_out = True
            break
        for name in dirnames + filenames:
            low = name.lower()
            ok = fnmatch.fnmatch(low, q) if is_glob else q in low
            if ok and (not exts or Path(low).suffix in exts):
                results.append(str(Path(dirpath) / name))
                if len(results) >= max_results:
                    return {"resultats": results, "limite_atteinte": True}
    return {"resultats": results, "temps_depasse": timed_out}


@registry.register(
    "file_info", "Donne les informations d'un fichier ou dossier (taille, dates, type).",
    {"path": param("string", "Chemin")}, ["path"])
def file_info(path: str) -> dict:
    p = resolve(path)
    st = p.stat()
    return {"chemin": str(p), "type": "dossier" if p.is_dir() else "fichier",
            "extension": p.suffix, "taille": human_size(st.st_size),
            "créé": datetime.fromtimestamp(st.st_ctime).isoformat(timespec="seconds"),
            "modifié": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}


# ---------------------------------------------------------------- ÉCRITURE (confirmation)
@registry.register(
    "create_file", "Crée un nouveau fichier avec un contenu.",
    {"path": param("string", "Chemin du fichier à créer"),
     "content": param("string", "Contenu du fichier")},
    ["path", "content"], confirm=True,
    summary=lambda a: f"Créer le fichier « {shown(a['path'])} » ({len(a.get('content', ''))} caractères) :\n"
                      f"{preview(a.get('content', ''))}")
def create_file(path: str, content: str) -> str:
    p = resolve(path)
    ensure_writable(p)
    if p.exists():
        raise FileExistsError(f"{p} existe déjà. Utilise modify_file pour le modifier.")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Fichier créé : {p}"


@registry.register(
    "modify_file",
    "Modifie un fichier texte : remplace tout le contenu (mode 'overwrite'), ajoute à la fin ('append'), "
    "ou remplace un passage précis ('replace' avec old_text et new_text).",
    {"path": param("string", "Chemin du fichier"),
     "mode": param("string", "Type de modification", enum=["overwrite", "append", "replace"]),
     "content": param("string", "Nouveau contenu (overwrite / append)"),
     "old_text": param("string", "Texte exact à remplacer (replace)"),
     "new_text": param("string", "Texte de remplacement (replace)")},
    ["path", "mode"], confirm=True,
    summary=lambda a: {
        "overwrite": f"Remplacer tout le contenu de « {shown(a['path'])} » par :\n{preview(a.get('content', ''))}",
        "append": f"Ajouter à la fin de « {shown(a['path'])} » :\n{preview(a.get('content', ''))}",
        "replace": f"Dans « {shown(a['path'])} », remplacer « {preview(a.get('old_text', ''), 120)} » "
                   f"par « {preview(a.get('new_text', ''), 120)} »",
    }.get(a.get("mode"), f"Modifier « {shown(a['path'])} »"))
def modify_file(path: str, mode: str, content: str = "", old_text: str = "", new_text: str = "") -> str:
    p = resolve(path)
    ensure_writable(p)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    if mode == "overwrite":
        p.write_text(content, encoding="utf-8")
    elif mode == "append":
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
    elif mode == "replace":
        text = p.read_text(encoding="utf-8")
        count = text.count(old_text)
        if not old_text or count == 0:
            raise ValueError("Texte à remplacer introuvable.")
        if count > 1:
            raise ValueError(f"Texte trouvé {count} fois : précise un passage plus long.")
        p.write_text(text.replace(old_text, new_text), encoding="utf-8")
    else:
        raise ValueError(f"Mode inconnu : {mode}")
    return f"Fichier modifié : {p}"


@registry.register(
    "create_directory", "Crée un dossier (et ses parents si besoin).",
    {"path": param("string", "Chemin du dossier")}, ["path"], confirm=True,
    summary=lambda a: f"Créer le dossier « {shown(a['path'])} »")
def create_directory(path: str) -> str:
    p = resolve(path)
    ensure_writable(p)
    p.mkdir(parents=True, exist_ok=True)
    return f"Dossier créé : {p}"


@registry.register(
    "move_file", "Déplace ou renomme un fichier ou un dossier.",
    {"source": param("string", "Chemin actuel"), "destination": param("string", "Nouveau chemin")},
    ["source", "destination"], confirm=True,
    summary=lambda a: f"Déplacer/renommer « {shown(a['source'])} » vers « {shown(a['destination'])} »")
def move_file(source: str, destination: str) -> str:
    src, dst = resolve(source), resolve(destination)
    ensure_writable(src)
    ensure_writable(dst)
    if dst.exists() and not dst.is_dir():
        raise FileExistsError(f"{dst} existe déjà.")
    return f"Déplacé vers : {shutil.move(str(src), str(dst))}"


@registry.register(
    "copy_file", "Copie un fichier ou un dossier.",
    {"source": param("string", "Chemin à copier"), "destination": param("string", "Chemin de la copie")},
    ["source", "destination"], confirm=True,
    summary=lambda a: f"Copier « {shown(a['source'])} » vers « {shown(a['destination'])} »")
def copy_file(source: str, destination: str) -> str:
    src, dst = resolve(source), resolve(destination)
    ensure_writable(dst)
    target = dst / src.name if dst.is_dir() else dst
    if target.exists():
        raise FileExistsError(f"{target} existe déjà : copie annulée pour ne rien écraser.")
    if src.is_dir():
        shutil.copytree(src, target)
    else:
        shutil.copy2(src, target)
    return f"Copié vers : {target}"


@registry.register(
    "delete_file", "Met un fichier ou un dossier à la corbeille (récupérable).",
    {"path": param("string", "Chemin exact à supprimer")}, ["path"], confirm=True,
    summary=lambda a: f"Mettre à la corbeille « {shown(a['path'])} »")
def delete_file(path: str) -> str:
    p = resolve(path)
    ensure_writable(p)
    if not p.exists():
        raise FileNotFoundError(str(p))
    send2trash(str(p))
    return f"Mis à la corbeille : {p}"


@registry.register(
    "open_file", "Ouvre un fichier pour l'utilisateur avec l'application par défaut (image, vidéo, PDF…).",
    {"path": param("string", "Chemin du fichier")}, ["path"], confirm=True,
    summary=lambda a: f"Ouvrir « {shown(a['path'])} » avec l'application par défaut")
def open_file(path: str) -> str:
    p = resolve(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    ctx.os.open_file(p)
    return f"Ouvert : {p}"


@registry.register(
    "reveal_in_explorer", "Montre un fichier dans l'explorateur de fichiers.",
    {"path": param("string", "Chemin du fichier")}, ["path"], confirm=True,
    summary=lambda a: f"Afficher « {shown(a['path'])} » dans l'explorateur")
def reveal_in_explorer(path: str) -> str:
    p = resolve(path)
    ctx.os.reveal(p)
    return f"Affiché : {p}"
