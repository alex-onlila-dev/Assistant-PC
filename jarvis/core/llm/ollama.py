"""Client du cerveau local (Ollama). Aucun appel à une API externe."""
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Callable

import httpx

from jarvis.core.llm.base import Delta, LLMClient, LLMError


def _exe() -> str | None:
    """ollama.exe, même s'il vient d'être installé et n'est pas encore dans le PATH de ce programme."""
    found = shutil.which("ollama")
    if found:
        return found
    if sys.platform.startswith("win"):
        default = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"
        return str(default) if default.exists() else None
    return None


class OllamaClient(LLMClient):
    provider = "ollama"
    label = "Local"
    nudge = True

    def __init__(self, host: str, model: str, vision_model: str | None = None,
                 timeout: int = 300, options: dict | None = None, keep_alive: str | int = "30m"):
        self.host = host.rstrip("/")
        self.model = model
        self.vision_model = vision_model
        self.timeout = timeout
        self.options = options or {}
        self.keep_alive = keep_alive   # garde le modèle en mémoire entre deux demandes : pas de rechargement

    @property
    def setup_hint(self) -> str:
        if not _exe():
            return ("Ollama n'est pas installé : installe-le (ollama.com), ou choisis Claude ou un autre service "
                    "dans Paramètres > Cerveau.")
        return "Ollama ne répond pas. Lance « ollama serve » puis redémarre Jarvis."

    @staticmethod
    def installed(host: str = "http://localhost:11434") -> bool:
        return _exe() is not None or OllamaClient(host, "").ping()

    def ping(self) -> bool:
        try:
            return httpx.get(f"{self.host}/api/tags", timeout=5).status_code == 200
        except httpx.HTTPError:
            return False

    def ensure_running(self, wait_seconds: float = 15) -> bool:
        """Démarre Ollama s'il est installé mais arrêté (ex. Jarvis lancé à l'ouverture de session)."""
        if self.ping():
            return True
        import subprocess
        import time

        exe = _exe()
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

    def pull(self, name: str, on_progress: Callable[[str, float | None], None]) -> None:
        """Télécharge un modèle (comme « ollama pull »). on_progress(étape, avancement 0..1 ou None)."""
        try:
            with httpx.stream("POST", f"{self.host}/api/pull", json={"model": name, "stream": True},
                              timeout=httpx.Timeout(30, read=None)) as r:
                if r.status_code >= 400:
                    r.read()
                    raise LLMError(f"Erreur Ollama : {r.text}")
                for line in r.iter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise LLMError(chunk["error"])
                    total, done = chunk.get("total"), chunk.get("completed")
                    on_progress(chunk.get("status", ""), done / total if total and done else None)
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama ne répond pas : {e}") from e

    def warm_up(self) -> None:
        """Charge le modèle en mémoire tout de suite, pour que la première réponse soit rapide."""
        try:
            httpx.post(f"{self.host}/api/generate", json={"model": self.model, "keep_alive": self.keep_alive},
                       timeout=self.timeout)
        except httpx.HTTPError:
            pass

    def prime(self, messages: list[dict], tools: list[dict]) -> None:
        """Fait lire au cerveau ses consignes et ses outils dès le démarrage.

        Ollama garde en cache le début de conversation déjà lu : la première vraie question n'a plus
        à relire ces milliers de mots (sinon plusieurs dizaines de secondes sur une petite machine).
        """
        self.chat(messages + [{"role": "user", "content": "Bonjour"}], tools=tools, options={"num_predict": 1})

    def chat(self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None,
             on_delta: Delta | None = None, options: dict | None = None) -> dict:
        """Renvoie le message de l'assistant : {"role", "content", "tool_calls"?}.

        on_delta : si fourni, la réponse arrive en continu et chaque morceau de texte lui est passé
                   dès qu'il est produit (pour commencer à parler sans attendre la fin).
        options  : réglages ponctuels ajoutés à ceux de la config (ex. num_predict).
        """
        payload = {
            "model": model or self.model,
            # « native » : réponse brute d'un autre cerveau (Claude), qu'Ollama n'a pas à lire
            "messages": [{k: v for k, v in m.items() if k != "native"} for m in messages],
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
        except httpx.TimeoutException as e:
            raise LLMError("Ollama met trop de temps à répondre (réglage « Attente maximale »).") from e
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:   # connexion coupée, réponse illisible
            raise LLMError(f"Échange avec Ollama interrompu : {e}") from e

    def describe_images(self, images_b64: list[str], prompt: str) -> str:
        """Fait « voir » une ou plusieurs images au modèle vision."""
        if not self.vision_model:
            raise LLMError("Aucun modèle vision configuré (llm.vision_model).")
        return super().describe_images(images_b64, prompt)


def _read_stream(lines, on_delta: Delta) -> dict:
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
