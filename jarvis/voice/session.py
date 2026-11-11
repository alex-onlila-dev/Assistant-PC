"""Conversation vocale façon appel téléphonique.

On réveille Jarvis une fois (voix ou claquement), puis on enchaîne les demandes sans le rappeler.
La conversation se termine sur une phrase de fin (« c'est tout », « on s'arrête là »…), après un silence,
ou si on touche la bulle à l'écran. Jarvis retourne alors en veille, prêt à être rappelé.

Cette classe ne dépend d'aucun affichage : elle prévient une « UI » (bulle à l'écran, ou simple terminal)
de chaque changement d'état.
"""
import random
import re
import threading

from jarvis.bootstrap import create_agent
from jarvis.config import USER_CONFIG, load_config
from jarvis.core.confirmation import Confirmer, parse_yes_no
from jarvis.core.context import ctx
from jarvis.core.llm import create_llm
from jarvis.core.tools import TOOL_LABELS
from jarvis.voice.activation import ActivationListener, strip_wake_word
from jarvis.voice.audio_io import beep, record_until_silence
from jarvis.voice.stt import get_transcriber
from jarvis.voice.tts import Speaker, SpeechStream

# Éteindre complètement Jarvis
QUIT_PHRASES = {"éteins-toi", "éteins toi", "quitte", "stop jarvis", "ferme-toi", "ferme toi"}

# Terminer la conversation (Jarvis reste en veille)
END_PHRASES = {
    "on s'arrête là", "on arrête là", "on s'arrête", "c'est tout", "c'est bon", "ça sera tout", "ce sera tout",
    "c'est tout pour moi", "c'est fini", "terminé", "fin de la conversation", "rien", "rien d'autre",
    "au revoir", "à plus", "à plus tard", "à tout à l'heure", "bonne nuit", "laisse tomber", "stop",
    "merci", "non merci",
}
# Mots qui entourent souvent une phrase de fin sans en changer le sens (« non merci, c'est tout Jarvis »)
_FILLERS = {"merci", "beaucoup", "jarvis", "ok", "okay", "d'accord", "non", "oui", "bon", "ben", "bah",
            "euh", "alors", "bien", "parfait", "c'est", "super", "génial", "top", "pour", "l'instant", "le", "moment"}

GOODBYES = ["D'accord, à plus tard.", "Très bien. Je reste disponible.", "Ça marche, à tout à l'heure."]

def _normalize(text: str) -> str:
    t = re.sub(r"[^\w\s'-]", " ", (text or "").lower().replace("’", "'"))
    return " ".join(t.split())


def is_quit_command(text: str) -> bool:
    """Vrai seulement si toute la phrase est un ordre d'arrêt : « dis-lui de quitter » ne compte pas."""
    return _normalize(text) in QUIT_PHRASES


def is_end_of_conversation(text: str) -> bool:
    """« c'est tout », « non merci c'est bon », « on s'arrête là Jarvis »… mais pas
    « c'est bon, maintenant ouvre Chrome » : il reste une vraie demande, la conversation continue."""
    t = _normalize(text)
    if t in END_PHRASES:
        return True
    words = t.split()
    for phrase in sorted(END_PHRASES, key=len, reverse=True):
        if phrase in t:
            rest = t.replace(phrase, " ").split()
            if all(w in _FILLERS for w in rest) and len(words) <= 8:
                return True
    return False


class SessionUI:
    """Ce que la session dit à l'affichage. Toutes les méthodes sont facultatives."""

    def ready(self, how: str) -> None: ...
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def state(self, name: str, detail: str = "") -> None: ...   # listening | thinking | speaking | confirm
    def level(self, value: float) -> None: ...                  # volume 0..1 (micro ou voix de Jarvis)
    def user_text(self, text: str) -> None: ...
    def answer_reset(self) -> None: ...
    def answer_delta(self, piece: str) -> None: ...


class VoiceConfirmer(Confirmer):
    """Demande la confirmation à voix haute et écoute « oui » / « non »."""

    def __init__(self, session: "VoiceSession"):
        self.s = session

    def ask(self, action: str) -> bool:
        s = self.s
        s.speech.flush()
        s.speech.wait()
        s.set_state("confirm", action)
        spoken = action.split("\n")[0]   # on lit l'action, pas l'aperçu du contenu (affiché à l'écran)
        s.speech.say(f"{spoken}. Je confirme ?")
        for _ in range(2):
            s.set_state("confirm", action)
            text = s.listen_once(timeout=6)
            if text:
                s.ui.user_text(text)
            answer = parse_yes_no(text)
            if answer is not None:
                s.set_state("speaking")
                s.speech.say("D'accord." if answer else "D'accord, j'annule.")
                s.set_state("thinking")
                return answer
            s.speech.say("Je n'ai pas compris. Oui ou non ?")
        s.speech.say("Pas de réponse claire, j'annule par sécurité.")
        s.set_state("thinking")
        return False


class VoiceSession:
    def __init__(self, cfg: dict, ui: SessionUI | None = None):
        self.cfg = cfg
        self.ui = ui or SessionUI()
        v = cfg.get("voice", {})
        self.silence = v.get("silence_seconds", 0.9)
        self.max_record = v.get("max_record_seconds", 20)
        self.followup = v.get("followup_seconds", 8)   # silence après une réponse avant de raccrocher

        self.speaker = Speaker(cfg)
        self.transcriber = get_transcriber(cfg)
        self.speech = SpeechStream(self.speaker, on_level=self._speaking_level)
        self.agent = create_agent(cfg, VoiceConfirmer(self), speaker=self.speaker, voice=True)
        self.agent.on_event = self._on_event
        self.listener = ActivationListener(cfg)
        self._config_mtime = self._config_time()

        self._state = "idle"
        self._streamed = False
        self.quit = threading.Event()        # éteindre Jarvis
        self.hang_up = threading.Event()     # terminer la conversation en cours
        self._interrupt = threading.Event()  # sortir de la veille (réveil manuel ou arrêt)

    # ------------------------------------------------------------ boucle principale
    def run(self) -> None:
        threading.Thread(target=self.agent.warm_up, daemon=True).start()
        self.ui.ready(self.listener.describe())
        try:
            while not self.quit.is_set():
                mode, audio = self.listener.listen(on_wake=self._on_wake, on_level=self.ui.level,
                                                   stop=self._interrupt)
                if self.quit.is_set():
                    break
                if mode is None:                          # réveil manuel (menu « Parler à Jarvis »)
                    self._interrupt.clear()
                    self._on_wake("manuel")
                    beep(1040, 0.08)
                    text = self.listen_once(timeout=self.followup)
                else:
                    self.set_state("thinking", "…")
                    text = strip_wake_word(self.transcriber.transcribe_array(audio))
                if not text and mode is not None:         # « Jarvis ! » puis silence
                    self.set_state("speaking")
                    self.speech.say("Oui ?")
                    text = self.listen_once(timeout=self.followup)
                self.converse(text)
                self.speech.interrupt()
                self.set_state("idle")
                self.ui.hide()
        finally:
            ctx.alarms.stop()

    def converse(self, text: str) -> None:
        """Enchaîne les échanges sans mot d'activation, jusqu'à la fin de la conversation."""
        self.hang_up.clear()
        self._refresh_brain()
        while text and not (self.hang_up.is_set() or self.quit.is_set()):
            self.ui.user_text(text)
            if is_quit_command(text):
                self.set_state("speaking")
                self.speech.say("À bientôt.")
                self.quit.set()
                return
            if is_end_of_conversation(text):
                self.set_state("speaking")
                self.ui.answer_reset()
                bye = random.choice(GOODBYES)
                self.ui.answer_delta(bye)
                self.speech.say(bye)
                return

            self.set_state("thinking")
            self.ui.answer_reset()
            self._streamed = False
            try:
                answer = self.agent.run(text, on_delta=self._on_delta)
            except Exception as e:                       # le mode vocal ne doit jamais s'arrêter sur une erreur
                print(f"Erreur pendant la réponse : {type(e).__name__}: {e}")
                answer, self._streamed = "Désolé, un problème est survenu. Réessaie.", False
            if not self._streamed and answer:            # erreur ou réponse non diffusée : on la dit quand même
                self._on_delta(answer)
            self.speech.flush()
            self.speech.wait()
            if self.hang_up.is_set():
                return
            text = self.listen_once(timeout=self.followup)
        # silence prolongé : on raccroche sans rien dire, comme Siri

    def listen_once(self, timeout: float) -> str:
        """Écoute une phrase (sans mot d'activation). Chaîne vide si personne ne parle."""
        if self.hang_up.is_set():
            return ""
        if self._state != "confirm":
            self.set_state("listening")
        audio = record_until_silence(self.silence, self.max_record, no_speech_timeout=timeout,
                                     on_level=self.ui.level, stop=self.hang_up)
        if len(audio) == 0:
            return ""
        if self._state != "confirm":
            self.set_state("thinking", "…")
        return strip_wake_word(self.transcriber.transcribe_array(audio))

    # ------------------------------------------------------------ commandes venues de l'affichage
    def end_conversation(self) -> None:
        """Toucher la bulle : on coupe la parole et on raccroche."""
        self.hang_up.set()
        self.speech.interrupt()

    def wake_now(self) -> None:
        """Démarrer une conversation sans mot d'activation (menu, raccourci…)."""
        if self._state == "idle":
            self._interrupt.set()

    def shutdown(self) -> None:
        self.quit.set()
        self._interrupt.set()
        self.end_conversation()

    # ------------------------------------------------------------ interne
    @staticmethod
    def _config_time() -> float:
        try:
            return USER_CONFIG.stat().st_mtime
        except OSError:
            return 0.0

    def _refresh_brain(self) -> None:
        """Les Paramètres s'ouvrent dans la fenêtre de discussion, un autre programme : si la configuration
        a changé depuis, on reprend le cerveau choisi (une clé API tout juste ajoutée, par exemple)."""
        mtime = self._config_time()
        if mtime == self._config_mtime:
            return
        self._config_mtime = mtime
        try:
            self.cfg["llm"] = load_config().get("llm", {})
            ctx.llm = self.agent.llm = create_llm(self.cfg)
        except Exception as e:
            print(f"Configuration illisible, cerveau inchangé : {e}")

    def set_state(self, name: str, detail: str = "") -> None:
        self._state = name
        self.ui.state(name, detail)

    def _on_wake(self, mode: str) -> None:
        self.hang_up.clear()          # un toucher de bulle pendant la conversation précédente ne compte plus
        self.ui.answer_reset()
        self.ui.user_text("")
        self.ui.show()
        self.set_state("listening")   # pas de bip en mode voix : il serait enregistré au milieu de ta phrase

    def _on_delta(self, piece: str) -> None:
        self._streamed = True
        self.ui.answer_delta(piece)
        self.speech.feed(piece)

    def _speaking_level(self, value: float) -> None:
        if value > 0 and self._state == "thinking":
            self.set_state("speaking")
        self.ui.level(value)

    def _on_event(self, kind: str, data: dict) -> None:
        if kind == "tool_start" and self._state in ("thinking", "speaking"):
            self.set_state("thinking", TOOL_LABELS.get(data["tool"], "Je m'en occupe…"))
