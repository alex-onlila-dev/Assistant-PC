"""Lecture d'un projet entier pour en donner un avis impartial."""
import os
from collections import Counter
from pathlib import Path

from jarvis.core.context import ctx
from jarvis.core.tools import param, registry
from jarvis.tools._paths import resolve

KEY_FILES = [
    "README.md", "README", "package.json", "requirements.txt", "pyproject.toml", "composer.json",
    "pom.xml", "build.gradle", "Cargo.toml", "go.mod", "Dockerfile", "docker-compose.yml",
    "manage.py", "settings.py", ".env.example", "tsconfig.json", "vite.config.ts", "vite.config.js",
]
CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".php", ".java", ".kt", ".go", ".rs", ".cs",
            ".c", ".cpp", ".h", ".rb", ".dart", ".swift", ".vue", ".svelte", ".html", ".css", ".scss", ".sql"}


def _tree(root: Path, skip: set, max_depth: int = 3, max_lines: int = 150) -> list[str]:
    lines: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = sorted(d for d in dirnames if d not in skip and not d.startswith("."))
        if depth >= max_depth:
            dirnames[:] = []
        indent = "  " * depth
        lines.append(f"{indent}{Path(dirpath).name}/")
        for f in sorted(filenames)[:25]:
            lines.append(f"{indent}  {f}")
        if len(lines) > max_lines:
            lines.append("…")
            break
    return lines


@registry.register(
    "review_project",
    "Parcourt un dossier de projet (structure, langages, fichiers clés, extraits de code) "
    "pour pouvoir donner un avis impartial dessus.",
    {"path": param("string", "Chemin du dossier du projet")}, ["path"])
def review_project(path: str) -> dict:
    root = resolve(path)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    skip = set(ctx.cfg.get("search", {}).get("skip_dirs", [])) | {"dist", "build", "vendor", "target"}

    ext_count: Counter = Counter()
    code_lines = 0
    biggest: list[tuple[int, str]] = []
    has_tests = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        if any(t in Path(dirpath).name.lower() for t in ("test", "spec")):
            has_tests = True
        for f in filenames:
            p = Path(dirpath) / f
            ext_count[p.suffix.lower() or "(sans)"] += 1
            if p.suffix.lower() in CODE_EXT:
                try:
                    n = sum(1 for _ in open(p, encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
                code_lines += n
                biggest.append((n, str(p.relative_to(root))))
            if "test" in f.lower():
                has_tests = True

    key_files = {}
    for name in KEY_FILES:
        for found in list(root.glob(name)) + list(root.glob(f"*/{name}"))[:2]:
            try:
                key_files[str(found.relative_to(root))] = found.read_text(encoding="utf-8", errors="ignore")[:3000]
            except OSError:
                pass

    biggest.sort(reverse=True)
    samples = {}
    for _, rel in biggest[:3]:
        samples[rel] = (root / rel).read_text(encoding="utf-8", errors="ignore")[:2500]

    return {
        "projet": str(root),
        "arborescence": "\n".join(_tree(root, skip)),
        "fichiers_par_extension": dict(ext_count.most_common(15)),
        "lignes_de_code": code_lines,
        "tests_detectes": has_tests,
        "plus_gros_fichiers": [f"{rel} ({n} lignes)" for n, rel in biggest[:10]],
        "fichiers_cles": key_files,
        "extraits_de_code": samples,
        "consigne": "Donne un avis impartial : points forts, faiblesses, risques de sécurité, "
                    "qualité de l'architecture, tests, documentation, pistes concrètes d'amélioration.",
    }
