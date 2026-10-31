"""Client du cerveau local (Ollama). Aucun appel à une API externe."""
import json
from typing import Callable

import httpx


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, host: str, model: str, vision_model: str | None = None,
                 timeout: int = 300, options: dict | None = None, keep_alive: str | int = "30m"):
        self.host = host.rstrip("/")
        self.model = model
        self.vision_model = vision_model
        self.timeout = timeout
        self.options = options or {}
        self.keep_alive = keep_alive   # garde le modèle en mémoire entre deux demandes : pas de rechargement

    def ping(self) -> bool:
        try:
            return httpx.get(f"{self.host}/api/tags", timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    def ensure_running(self, wait_seconds: float = 15) -> bool:
        """Démarre Ollama s'il est installé mais arrêté (ex. Jarvis lancé à l'ouverture de session)."""
        if self.ping():
            return True
        import shutil
        import subprocess
        import sys
        import time

        exe = shutil.which("ollama")
        if not exe or ("localhost" not in self.host and "127.0.0.1" not in self.host):
            return False
        flags = {"creationflags": 0x08000000} if sys.platform.startswith("win") else {"start_new_session": True}
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            time.sleep(0.5)
            if self.ping():
                return True
        return False

    def installed_models(self) -> list[str]:
        r = httpx.get(f"{self.host}/api/tags", timeout=10)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def warm_up(self) -> None:
        """Charge le modèle en mémoire tout de suite, pour que la première réponse soit rapide."""
        try:
            httpx.post(f"{self.host}/api/generate", json={"model": self.model, "keep_alive": self.keep_alive},
                       timeout=self.timeout)
        except httpx.HTTPError:
            pass

    def chat(self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None,
             on_delta: Callable[[str], None] | None = None, options: dict | None = None) -> dict:
        """Renvoie le message de l'assistant : {"role", "content", "tool_calls"?}.

        on_delta : si fourni, la réponse arrive en continu et chaque morceau de texte lui est passé
                   dès qu'il est produit (pour commencer à parler sans attendre la fin).
        options  : réglages ponctuels ajoutés à ceux de la config (ex. num_predict).
        """
        payload = {
            "model": model or self.model,
            "messages": messages,
            "stream": on_delta is not None,
            "options": {**self.options, **(options or {})},
            "keep_alive": self.keep_alive,
        }
        if tools:
            payload["tools"] = tools
        try:
            if on_delta is None:
                r = httpx.post(f"{self.host}/api/chat", json=payload, timeout=self.timeout)
                r.raise_for_status()
                return r.json()["message"]
            with httpx.stream("POST", f"{self.host}/api/chat", json=payload, timeout=self.timeout) as r:
                if r.status_code >= 400:
                    r.read()
                    r.raise_for_status()
                return _read_stream(r.iter_lines(), on_delta)
        except httpx.ConnectError as e:
            raise LLMError("Ollama ne répond pas. Lance-le avec : ollama serve") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(f"Erreur Ollama : {e.response.text}") from e

    def describe_images(self, images_b64: list[str], prompt: str) -> str:
        """Fait « voir » une ou plusieurs images au modèle vision."""
        if not self.vision_model:
            raise LLMError("Aucun modèle vision configuré (llm.vision_model).")
        msg = {"role": "user", "content": prompt, "images": images_b64}
        return self.chat([msg], model=self.vision_model).get("content", "")


def _read_stream(lines, on_delta: Callable[[str], None]) -> dict:
    """Assemble le message à partir des lignes JSON envoyées par Ollama en mode continu."""
    content, tool_calls = [], []
    for line in lines:
        if not line.strip():
            continue
        chunk = json.loads(line)
        if "error" in chunk:
            raise LLMError(f"Erreur Ollama : {chunk['error']}")
        msg = chunk.get("message", {})
        piece = msg.get("content", "")
        if piece:
            content.append(piece)
            on_delta(piece)
        tool_calls.extend(msg.get("tool_calls") or [])
        if chunk.get("done"):
            break
    result = {"role": "assistant", "content": "".join(content)}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return result
