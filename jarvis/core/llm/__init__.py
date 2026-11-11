"""Le cerveau de Jarvis, au choix :

- « ollama » : un modèle qui tourne sur l'ordinateur, sans Internet ;
- « claude » : Claude, avec une clé API Anthropic ;
- « openai » : n'importe quel service compatible OpenAI (OpenAI, Mistral, Groq, OpenRouter, Gemini…) ;
- « auto »   : Ollama s'il est installé, sinon le premier service en ligne dont la clé est renseignée.
"""
import os

from jarvis.core.llm.base import LLMClient, LLMError
from jarvis.core.llm.ollama import OllamaClient

__all__ = ["LLMClient", "LLMError", "OllamaClient", "create_llm", "resolve_provider"]


def resolve_provider(cfg: dict) -> str:
    llm = cfg.get("llm", {})
    provider = llm.get("provider", "auto")
    if provider != "auto":
        return provider
    if OllamaClient.installed(llm.get("host", "http://localhost:11434")):
        return "ollama"
    if (llm.get("claude") or {}).get("api_key") or os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if (llm.get("openai") or {}).get("api_key"):
        return "openai"
    return "ollama"     # rien de configuré : le message d'erreur d'Ollama explique quoi faire


def create_llm(cfg: dict) -> LLMClient:
    llm = cfg.get("llm", {})
    provider = resolve_provider(cfg)
    timeout = llm.get("timeout", 300)
    if provider == "claude":
        from jarvis.core.llm.claude import DEFAULT_MODEL, ClaudeClient
        c = llm.get("claude") or {}
        return ClaudeClient(api_key=c.get("api_key", ""), model=c.get("model") or DEFAULT_MODEL,
                            effort=c.get("effort", "medium"), timeout=timeout, fallback=c.get("fallback", True))
    if provider == "openai":
        from jarvis.core.llm.openai_compat import OpenAICompatClient
        o = llm.get("openai") or {}
        return OpenAICompatClient(base_url=o.get("base_url", ""), api_key=o.get("api_key", ""),
                                  model=o.get("model", ""), vision_model=o.get("vision_model", ""), timeout=timeout,
                                  temperature=(llm.get("options") or {}).get("temperature"))
    return OllamaClient(
        host=llm.get("host", "http://localhost:11434"),
        model=llm.get("model", "qwen2.5:7b"),
        vision_model=llm.get("vision_model"),
        timeout=timeout,
        options=llm.get("options", {}),
        keep_alive=llm.get("keep_alive", "30m"),
    )
