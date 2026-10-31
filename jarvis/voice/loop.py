"""Mode vocal dans le terminal (sans bulle à l'écran). Même conversation que la bulle, affichée en texte."""
from jarvis.core.context import ctx
from jarvis.voice.session import SessionUI, VoiceSession

_LABELS = {"listening": "🎙️  J'écoute…", "thinking": "🧠 Je réfléchis…", "confirm": "⚠️  Confirmation"}


class ConsoleUI(SessionUI):
    def __init__(self):
        self._last = ""

    def ready(self, how: str) -> None:
        print(f"Jarvis est prêt. Pour me parler, {how}. Ctrl+C pour quitter.")

    def state(self, name: str, detail: str = "") -> None:
        line = _LABELS.get(name, "")
        if name == "confirm":
            line = f"\n⚠️  {detail}"
        elif detail and detail != "…":
            line = f"   ⚙️  {detail}"
        if line and line != self._last:
            print(line)
            self._last = line

    def user_text(self, text: str) -> None:
        if text:
            print(f"\nToi : {text}")

    def answer_reset(self) -> None:
        self._started = False

    def answer_delta(self, piece: str) -> None:
        if not getattr(self, "_started", False):
            print("Jarvis : ", end="")
            self._started = True
        print(piece, end="", flush=True)

    def hide(self) -> None:
        print("\n— fin de la conversation, je reste en veille —")


def run_voice(cfg: dict) -> int:
    print("Chargement de la voix…")
    session = VoiceSession(cfg, ConsoleUI())
    if not ctx.llm.ping():
        print("⚠️  Ollama ne répond pas. Lance « ollama serve » puis relance Jarvis.")
        return 1
    try:
        session.run()
    except KeyboardInterrupt:
        session.shutdown()
    return 0
