"""Contexte partagé : les outils y trouvent la config, le cerveau, l'adaptateur OS, etc."""


class Context:
    cfg: dict = {}
    llm = None       # OllamaClient
    os = None        # OSAdapter
    memory = None    # Memory
    alarms = None    # AlarmService
    speaker = None   # Speaker (voix), optionnel


ctx = Context()
