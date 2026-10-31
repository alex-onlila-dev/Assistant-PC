"""Mode texte dans le terminal."""
from jarvis.bootstrap import create_agent
from jarvis.core.confirmation import CLIConfirmer
from jarvis.core.context import ctx

HELP = """Commandes :
  /reset   nouvelle conversation
  /outils  liste des outils
  /quit    quitter
"""


def _event(kind: str, data: dict) -> None:
    if kind == "tool_start":
        print(f"   ⚙️  {data['tool']}…")
    elif kind == "cancelled":
        print("   ✖  Action annulée.")


def run_cli(cfg: dict) -> int:
    agent = create_agent(cfg, CLIConfirmer())
    agent.on_event = _event

    if not ctx.llm.ensure_running():
        print("⚠️  Ollama ne répond pas. Lance « ollama serve » dans un autre terminal.")
        return 1
    models = ctx.llm.installed_models()
    wanted = ctx.llm.model if ":" in ctx.llm.model else f"{ctx.llm.model}:latest"
    if wanted not in models:   # « qwen2.5:7b » installé ne veut pas dire « qwen2.5:3b » installé
        print(f"⚠️  Modèle {ctx.llm.model} absent. Installe-le : ollama pull {ctx.llm.model}")

    print(f"Jarvis prêt ({ctx.os.name}, cerveau : {ctx.llm.model}). /aide pour l'aide.\n")
    try:
        while True:
            text = input("Toi > ").strip()
            if not text:
                continue
            if text in ("/quit", "/exit"):
                break
            if text == "/reset":
                agent.reset()
                print("Nouvelle conversation.\n")
                continue
            if text == "/outils":
                print(", ".join(agent.registry.names()) + "\n")
                continue
            if text in ("/aide", "/help"):
                print(HELP)
                continue
            print(f"\nJarvis > {agent.run(text)}\n")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        ctx.alarms.stop()
    return 0
