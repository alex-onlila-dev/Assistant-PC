"""Assemble toutes les briques : cerveau, OS, mémoire, alarmes, outils."""
from jarvis.core.agent import Agent
from jarvis.core.alarms import AlarmService
from jarvis.core.confirmation import Confirmer
from jarvis.core.context import ctx
from jarvis.core.llm import OllamaClient
from jarvis.core.memory import Memory
from jarvis.core.tools import registry
from jarvis.os_adapters import get_adapter


def create_agent(cfg: dict, confirmer: Confirmer, speaker=None, voice: bool = False) -> Agent:
    llm_cfg = cfg.get("llm", {})
    ctx.cfg = cfg
    ctx.llm = OllamaClient(
        host=llm_cfg.get("host", "http://localhost:11434"),
        model=llm_cfg.get("model", "qwen2.5:7b"),
        vision_model=llm_cfg.get("vision_model"),
        timeout=llm_cfg.get("timeout", 300),
        options=llm_cfg.get("options", {}),
        keep_alive=llm_cfg.get("keep_alive", "30m"),
    )
    ctx.os = get_adapter()
    ctx.memory = Memory(cfg["data_dir"])
    ctx.speaker = speaker
    ctx.alarms = AlarmService(ctx.memory, on_ring=_ring)
    ctx.alarms.start()

    # L'import enregistre les outils dans le registre.
    import jarvis.tools  # noqa: F401

    return Agent(llm=ctx.llm, registry=registry, confirmer=confirmer, cfg=cfg, memory=ctx.memory, voice=voice)


def _ring(label: str) -> None:
    ctx.os.notify("⏰ Jarvis", label)
    if ctx.speaker:
        ctx.speaker.say(f"Rappel : {label}")
    else:
        print(f"\a\n⏰ ALARME : {label}\n")
