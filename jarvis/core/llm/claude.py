"""Cerveau Claude (API Anthropic) : une clé API suffit, rien à installer ni à faire tourner sur la machine.

Trois points propres à Claude :
- Ses réponses contiennent des blocs de réflexion signés qu'il faut lui renvoyer tels quels : on garde la
  réponse brute dans message["native"] et on la rejoue à l'identique.
- Ces blocs sont liés à la conversation exacte qui les a produits. Jarvis la modifie parfois (anciens
  échanges oubliés, consignes régénérées à la réouverture d'une conversation) : « drop_block » demande à
  l'API d'ignorer les blocs devenus invalides au lieu de refuser la requête.
- Consignes et outils (plusieurs milliers de mots, identiques à chaque étape) sont mis en cache :
  relus à une fraction du prix.
"""
from jarvis.core.llm.base import Delta, LLMClient, LLMError, arguments, is_error_result, with_call_ids

DEFAULT_MODEL = "claude-opus-5-5"
THINKING_BETA = "thinking-binding-controls-2026-08-01"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Après un changement de modèle en cours de réponse, ces blocs d'avant la bascule ne se renvoient pas
_DROPPED_BEFORE_FALLBACK = {"thinking", "redacted_thinking", "tool_use", "server_tool_use"}


class ClaudeClient(LLMClient):
    provider = "claude"
    label = "Claude"

    def __init__(self, api_key: str = "", model: str = DEFAULT_MODEL, effort: str = "medium",
                 max_tokens: int = 64000, timeout: int = 300, fallback: bool = True):
        self.model = model or DEFAULT_MODEL
        self.vision_model = None       # Claude voit les images lui-même
        self.effort = effort or "medium"
        self.max_tokens = max_tokens
        self.fallback = fallback
        self.client = None
        self._problem = ""
        try:
            import anthropic
        except ImportError:
            self._problem = "Module « anthropic » absent : relance l'installateur (ou pip install anthropic)."
            return
        no_key = "Aucune clé API Claude : ajoute-la dans Paramètres > Cerveau (à créer sur console.anthropic.com)."
        try:
            # Sans clé dans la config : variable ANTHROPIC_API_KEY, ou profil « ant auth login »
            client = anthropic.Anthropic(api_key=api_key or None, timeout=timeout)
        except anthropic.AnthropicError:
            self._problem = no_key
            return
        # Le SDK ne signale l'absence d'identifiants qu'à la première requête : on vérifie tout de suite
        if any(getattr(client, name, None) for name in ("api_key", "auth_token", "credentials")):
            self.client = client
        else:
            self._problem = no_key

    @property
    def setup_hint(self) -> str:
        return self._problem or "Claude n'est pas prêt : vérifie la clé API dans Paramètres > Cerveau."

    def ensure_running(self) -> bool:
        return self.client is not None

    def chat(self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None,
             on_delta: Delta | None = None, options: dict | None = None) -> dict:
        if self.client is None:
            raise LLMError(self.setup_hint)
        import anthropic

        system, msgs = to_claude(messages)
        model = model or self.model
        params = {
            "model": model,
            "max_tokens": self.max_tokens,     # la réflexion compte dedans
            "messages": msgs,
            "cache_control": {"type": "ephemeral"},
            "thinking": {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
            "output_config": {"effort": self.effort},
            "betas": [THINKING_BETA],
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = [claude_tool(t) for t in tools]
        if self.fallback and "haiku" not in model:   # Haiku n'a pas de modèle de repli
            params["fallbacks"] = "default"           # en cas de refus, un autre modèle Claude reprend la demande
            params["betas"].append(FALLBACK_BETA)

        try:
            with self.client.beta.messages.stream(**params) as stream:
                for piece in stream.text_stream:
                    if on_delta:
                        on_delta(piece)
                final = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMError("Clé API Claude refusée : vérifie-la dans Paramètres > Cerveau.") from e
        except anthropic.PermissionDeniedError as e:
            raise LLMError(f"Cette clé API n'a pas accès à ce modèle : {e.message}") from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"Modèle Claude inconnu : {model}") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Limite d'utilisation de Claude atteinte : réessaie dans un moment.") from e
        except anthropic.BadRequestError as e:          # crédit épuisé, requête invalide…
            raise LLMError(f"Claude a refusé la requête : {e.message}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Erreur du service Claude ({e.status_code}) : {e.message}") from e
        except anthropic.APIConnectionError as e:       # pas d'Internet, délai dépassé
            raise LLMError("Impossible de joindre Claude : vérifie la connexion Internet.") from e

        return from_claude([b.to_dict(mode="json") for b in final.content], final.stop_reason)


# ---------------------------------------------------------------------------------------- traduction
def claude_tool(schema: dict) -> dict:
    """Outil au format Ollama/OpenAI -> outil Claude.

    Sans « eager_input_streaming » : Jarvis n'affiche pas les arguments pendant qu'ils s'écrivent, et pour
    des outils qui modifient des fichiers, mieux vaut des arguments vérifiés par l'API que reçus plus tôt.
    """
    fn = schema["function"]
    return {"name": fn["name"], "description": fn["description"], "input_schema": fn["parameters"]}


def to_claude(messages: list[dict]) -> tuple[str, list[dict]]:
    """Historique Jarvis -> (consignes, messages Claude).

    Toujours la même traduction pour le même historique : la conversation envoyée ne change pas d'une
    étape à l'autre, sauf ce qui s'ajoute à la fin (condition du cache et des blocs de réflexion).
    """
    system, out = "", []

    def add(role: str, blocks: list[dict]) -> None:
        if not blocks:
            return
        if out and out[-1]["role"] == role:     # résultats de plusieurs outils appelés ensemble
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for i, m in enumerate(with_call_ids(messages)):
        role, content = m.get("role"), str(m.get("content") or "")
        if role == "system":
            if i == 0:
                system = content
            else:                                 # consigne ajoutée en cours de route (anciennes conversations)
                add("user", [{"type": "text", "text": f"[Consigne de Jarvis] {content}"}])
        elif role == "user":
            blocks = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img}}
                      for img in m.get("images") or []]
            add("user", blocks + ([{"type": "text", "text": content}] if content.strip() else []))
        elif role == "assistant":
            native = m.get("native") or {}
            if native.get("provider") == "claude":
                add("assistant", native["content"])
                continue
            blocks = [{"type": "text", "text": content}] if content.strip() else []
            blocks += [{"type": "tool_use", "id": c["id"], "name": c.get("function", {}).get("name", ""),
                        "input": arguments(c)} for c in m.get("tool_calls") or []]
            add("assistant", blocks)
        elif role == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": content}
            if is_error_result(content):
                block["is_error"] = True
            add("user", [block])

    while out and out[0]["role"] != "user":       # une conversation commence toujours par l'utilisateur
        out.pop(0)
    return system, out


def from_claude(blocks: list[dict], stop_reason: str | None) -> dict:
    """Réponse Claude -> message assistant Jarvis (avec la réponse brute à rejouer)."""
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if stop_reason == "refusal":
        return {"role": "assistant", "content": "Claude a refusé de traiter cette demande."}

    # Bascule sur un modèle de repli en cours de réponse : on ne renvoie pas ce que le premier préparait
    last_fallback = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=-1)
    kept = [b for i, b in enumerate(blocks) if i > last_fallback or b.get("type") not in _DROPPED_BEFORE_FALLBACK]
    uses = [b for b in kept if b.get("type") == "tool_use"]

    if uses and stop_reason == "max_tokens":
        # Appel d'outil coupé en plein milieu : on ne l'exécute pas, et on ne le garde pas (il resterait sans réponse)
        return {"role": "assistant", "content": (text + "\n\n(réponse coupée : trop longue)").strip()}

    msg = {"role": "assistant", "content": text, "native": {"provider": "claude", "content": kept}}
    if uses:
        msg["tool_calls"] = [{"id": b["id"], "function": {"name": b["name"], "arguments": b.get("input") or {}}}
                             for b in uses]
    return msg
