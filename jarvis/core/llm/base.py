"""Ce que tout cerveau sait faire, et les outils partagés pour traduire l'historique.

L'historique de la boucle agent suit le format d'Ollama :
    {"role": "system" | "user" | "assistant" | "tool", "content": "...",
     "tool_calls": [{"id", "function": {"name", "arguments"}}],   # assistant
     "tool_call_id": "...", "tool_name": "...",                    # tool
     "images": ["<base64>"],                                       # user (vision)
     "native": {"provider": "claude", "content": [...]}}           # assistant : réponse brute à renvoyer telle quelle
Chaque client le traduit vers son API et renvoie un message assistant dans ce même format.
"""
import json
from typing import Callable

Delta = Callable[[str], None]


class LLMError(RuntimeError):
    pass


class LLMClient:
    provider = ""
    label = ""          # affiché en bas de la fenêtre : « Local », « Claude »…
    nudge = False       # relancer le cerveau s'il écrit un appel d'outil au lieu de le faire (petits modèles)
    model = ""
    vision_model: str | None = None

    @property
    def setup_hint(self) -> str:
        """Ce qu'il faut faire quand ensure_running() renvoie False."""
        return "Le cerveau n'est pas prêt : vérifie Paramètres > Cerveau."

    def ensure_running(self) -> bool:
        """Vrai si le cerveau peut répondre (Ollama démarré, clé API présente…)."""
        return True

    def prime(self, messages: list[dict], tools: list[dict]) -> None:
        """Préparation au démarrage (rien à faire pour un service en ligne)."""

    def chat(self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None,
             on_delta: Delta | None = None, options: dict | None = None) -> dict:
        raise NotImplementedError

    def describe_images(self, images_b64: list[str], prompt: str) -> str:
        """Fait « voir » une ou plusieurs images (JPEG en base64)."""
        msg = {"role": "user", "content": prompt, "images": images_b64}
        return self.chat([msg], model=self.vision_model or self.model).get("content", "")


def arguments(call: dict) -> dict:
    """Arguments d'un appel d'outil, qu'ils arrivent en objet ou en texte JSON."""
    args = call.get("function", {}).get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {}
    return args if isinstance(args, dict) else {}


def with_call_ids(messages: list[dict]) -> list[dict]:
    """Copie de l'historique où chaque appel d'outil et chaque résultat portent un identifiant.

    Claude et les services OpenAI relient un résultat à son appel par identifiant ; Ollama n'en donne pas
    toujours, et les conversations enregistrées avant n'en ont pas : on associe alors dans l'ordre.
    """
    out, pending = [], []
    for i, m in enumerate(messages):
        m = dict(m)
        if m.get("role") == "assistant" and m.get("tool_calls"):
            m["tool_calls"] = [{**c, "id": c.get("id") or f"call_{i}_{j}"} for j, c in enumerate(m["tool_calls"])]
            pending = [c["id"] for c in m["tool_calls"]]
        elif m.get("role") == "tool":
            if m.get("tool_call_id") in pending:
                pending.remove(m["tool_call_id"])
            elif not m.get("tool_call_id"):
                m["tool_call_id"] = pending.pop(0) if pending else f"call_{i}"
        out.append(m)
    return out


def is_error_result(content: str) -> bool:
    """Résultat d'outil en échec (format écrit par Agent._execute)."""
    return content.startswith('{"statut": "erreur"')
