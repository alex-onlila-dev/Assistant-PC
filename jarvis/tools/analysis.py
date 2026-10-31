"""Analyse de n'importe quel fichier par Jarvis lui-même (lecture seule, sans confirmation)."""
from jarvis.analyzers import analyze
from jarvis.core.tools import param, registry
from jarvis.tools._paths import resolve


@registry.register(
    "analyze_file",
    "Analyse le contenu de n'importe quel fichier (image, audio, vidéo, PDF, Word, Excel, PowerPoint, "
    "archive, code, binaire) et renvoie ce qu'il contient pour en faire un rapport.",
    {"path": param("string", "Chemin du fichier"),
     "question": param("string", "Question précise sur le fichier (optionnel)")},
    ["path"])
def analyze_file(path: str, question: str = "") -> dict:
    p = resolve(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return analyze(p, question or None)
