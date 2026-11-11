"""Cerveau fourni par un service compatible OpenAI : OpenAI, Mistral, Groq, OpenRouter, DeepSeek, Gemini…
ou un serveur local comme LM Studio. Il suffit de son adresse, d'une clé API et du nom du modèle.
"""
import json

import httpx

from jarvis.core.llm.base import Delta, LLMClient, LLMError, arguments, with_call_ids

# Adresses connues, proposées dans les Paramètres (on peut en taper une autre)
PRESETS = [
    ("https://api.openai.com/v1", "OpenAI"),
    ("https://api.mistral.ai/v1", "Mistral"),
    ("https://api.groq.com/openai/v1", "Groq"),
    ("https://openrouter.ai/api/v1", "OpenRouter (des centaines de modèles)"),
    ("https://api.deepseek.com/v1", "DeepSeek"),
    ("https://generativelanguage.googleapis.com/v1beta/openai", "Google Gemini"),
    ("http://localhost:1234/v1", "LM Studio (sur cet ordinateur)"),
]


class OpenAICompatClient(LLMClient):
    provider = "openai"
    nudge = True       # on ne sait pas quel modèle répond : la relance reste utile pour les petits

    def __init__(self, base_url: str, api_key: str = "", model: str = "", vision_model: str = "",
                 timeout: int = 300, temperature: float | None = None):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model
        self.vision_model = vision_model or None
        self.timeout = timeout
        self.temperature = temperature
        self.label = next((name.split(" (")[0] for url, name in PRESETS if url == self.base_url), "En ligne")

    @property
    def setup_hint(self) -> str:
        if not self.base_url:
            return "Indique l'adresse du service dans Paramètres > Cerveau."
        return "Indique le nom du modèle à utiliser dans Paramètres > Cerveau."

    def ensure_running(self) -> bool:
        return bool(self.base_url and self.model)

    def chat(self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None,
             on_delta: Delta | None = None, options: dict | None = None) -> dict:
        if not self.ensure_running():
            raise LLMError(self.setup_hint)
        payload = {"model": model or self.model, "messages": to_openai(messages), "stream": True}
        if tools:
            payload["tools"] = tools          # le format des outils de Jarvis est déjà celui d'OpenAI
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            with httpx.stream("POST", f"{self.base_url}/chat/completions", json=payload, headers=headers,
                              timeout=self.timeout) as r:
                if r.status_code >= 400:
                    r.read()
                    raise LLMError(_error_text(r))
                return read_sse(r.iter_lines(), on_delta)
        except httpx.TimeoutException as e:
            raise LLMError("Le service met trop de temps à répondre.") from e
        except httpx.HTTPError as e:
            raise LLMError(f"Impossible de joindre {self.base_url} : {e}") from e
        except json.JSONDecodeError as e:
            raise LLMError(f"Réponse illisible du service : {e}") from e


def _error_text(r: httpx.Response) -> str:
    if r.status_code in (401, 403):
        return "Clé API refusée par le service : vérifie-la dans Paramètres > Cerveau."
    try:
        detail = r.json().get("error", {})
        detail = detail.get("message", detail) if isinstance(detail, dict) else detail
    except ValueError:
        detail = r.text[:300]
    if r.status_code == 404:
        return f"Modèle ou adresse inconnus ({detail})"
    if r.status_code == 429:
        return f"Limite d'utilisation atteinte : {detail}"
    return f"Erreur du service ({r.status_code}) : {detail}"


def to_openai(messages: list[dict]) -> list[dict]:
    """Historique Jarvis -> messages « chat completions »."""
    out = []
    for m in with_call_ids(messages):
        role, content = m.get("role"), str(m.get("content") or "")
        if role == "tool":
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": content})
        elif role == "assistant":
            msg = {"role": "assistant", "content": content}
            if m.get("tool_calls"):
                msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                      "function": {"name": c.get("function", {}).get("name", ""),
                                                   "arguments": json.dumps(arguments(c), ensure_ascii=False)}}
                                     for c in m["tool_calls"]]
            out.append(msg)
        elif role == "user" and m.get("images"):
            out.append({"role": "user", "content": [{"type": "text", "text": content}] + [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}} for img in m["images"]]})
        else:
            out.append({"role": role, "content": content})
    return out


def read_sse(lines, on_delta: Delta | None) -> dict:
    """Assemble la réponse envoyée en continu (« data: {...} ») : texte et appels d'outils en morceaux."""
    content, calls = [], {}
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        chunk = json.loads(data)
        if chunk.get("error"):
            err = chunk["error"]
            raise LLMError(f"Erreur du service : {err.get('message', err) if isinstance(err, dict) else err}")
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if delta.get("content"):
                content.append(delta["content"])
                if on_delta:
                    on_delta(delta["content"])
            for tc in delta.get("tool_calls") or []:
                slot = calls.setdefault(tc.get("index", len(calls)), {"id": "", "name": "", "arguments": ""})
                fn = tc.get("function") or {}
                slot["id"] = tc.get("id") or slot["id"]
                slot["name"] += fn.get("name") or ""
                slot["arguments"] += fn.get("arguments") or ""
    result = {"role": "assistant", "content": "".join(content)}
    if calls:
        result["tool_calls"] = [{"id": s["id"], "function": {"name": s["name"], "arguments": s["arguments"] or "{}"}}
                                for _, s in sorted(calls.items())]
    return result
