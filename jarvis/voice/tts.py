"""Texte -> voix. Piper (voix naturelle, hors ligne) sinon pyttsx3 (voix du système).

SpeechStream permet de parler pendant que le cerveau écrit encore la suite : chaque phrase terminée
est synthétisée puis jouée tout de suite, la suivante se prépare pendant la lecture.
"""
import os
import queue
import re
import tempfile
import threading
import wave
from pathlib import Path

from jarvis.config import ROOT
from jarvis.voice.audio_io import play_audio

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")


def _clean(text: str) -> str:
    """Retire le formatage Markdown et les emojis pour une lecture naturelle."""
    text = re.sub(r"```.*?```", " (bloc de code) ", text, flags=re.S)
    text = re.sub(r"[*_#`>|]", "", text)
    text = _EMOJI.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


_SENTENCE_END = re.compile(r"(?<=[.!?…:;])\s+|\n+")


def split_sentences(buffer: str, min_chars: int = 20) -> tuple[list[str], str]:
    """Découpe le texte reçu en phrases complètes ; renvoie (phrases prêtes, reste en attente).

    Les phrases très courtes sont regroupées avec la suivante pour éviter un débit haché.
    """
    parts = _SENTENCE_END.split(buffer)
    rest = parts.pop()                    # le dernier morceau n'est pas forcément fini
    ready, pending = [], ""
    for p in parts:
        pending = f"{pending} {p}".strip() if pending else p.strip()
        if len(pending) >= min_chars:
            ready.append(pending)
            pending = ""
    if pending:
        rest = f"{pending} {rest}".strip()
    return ready, rest


def pick_voice(voices, wanted: str = "") -> str | None:
    """Choisit la voix système : celle demandée par son nom, sinon une voix française de France.

    On regarde la langue déclarée (fr_FR), pas l'identifiant : « Fred » contient « fr » mais parle anglais.
    Les voix « eloquence » de macOS sont plus robotiques : elles passent après les autres.
    """
    voices = list(voices)
    if wanted:
        for v in voices:
            if wanted.lower() in (v.name or v.id).lower():
                return v.id

    def lang(v) -> str:
        langs = getattr(v, "languages", None) or []
        first = langs[0] if langs else ""
        if isinstance(first, bytes):
            first = first.decode(errors="ignore")
        return str(first).lower().replace("-", "_")

    def rank(v) -> tuple:
        return (lang(v) != "fr_fr", "eloquence" in v.id.lower())

    french = [v for v in voices if lang(v).startswith("fr")]
    return min(french, key=rank).id if french else None


class Speaker:
    def __init__(self, cfg: dict):
        self._lock = threading.Lock()
        self.backend = "print"
        model = cfg.get("voice", {}).get("piper_model", "")
        if model and not Path(model).expanduser().is_absolute():
            model = str(ROOT / model)   # « models/… » part du dossier du projet, d'où qu'on lance Jarvis
        if model and not Path(model).exists():
            print(f"[voix] Modèle Piper introuvable : {model}, repli sur la voix système.")
        elif model:
            try:
                from piper import PiperVoice
                self.voice = PiperVoice.load(model)
                self.backend = "piper"
            except Exception as e:
                print(f"[voix] Piper indisponible ({e}), repli sur pyttsx3.")
        if self.backend == "print":
            try:
                import pyttsx3
                self.engine = pyttsx3.init()
                voice = pick_voice(self.engine.getProperty("voices"),
                                   cfg.get("voice", {}).get("system_voice", ""))
                if voice:
                    self.engine.setProperty("voice", voice)
                self.backend = "pyttsx3"
            except Exception as e:
                print(f"[voix] Synthèse vocale indisponible ({e}), réponses en texte uniquement.")

    def synthesize(self, text: str):
        """Piper : renvoie (audio float32, fréquence). None pour les autres moteurs."""
        if self.backend != "piper":
            return None
        import numpy as np

        if not hasattr(self.voice, "synthesize_wav"):          # piper-tts < 1.3 : passe par un .wav
            return self._synthesize_old(text)
        chunks = list(self.voice.synthesize(text))
        if not chunks:
            return None
        return np.concatenate([c.audio_float_array for c in chunks]), chunks[0].sample_rate

    def _synthesize_old(self, text: str):
        import numpy as np

        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            with wave.open(path, "wb") as wf:
                self.voice.synthesize(text, wf)
            with wave.open(path, "rb") as wf:
                pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                return pcm.astype("float32") / 32768, wf.getframerate()
        finally:
            os.remove(path)

    def play(self, text: str, audio=None, on_level=None, stop=None) -> None:
        """Joue une phrase déjà nettoyée (audio déjà synthétisé si Piper)."""
        with self._lock:
            if audio is not None:
                play_audio(audio[0], audio[1], on_level=on_level, stop=stop)
            elif self.backend == "pyttsx3":
                self.engine.say(text)
                self.engine.runAndWait()
            else:
                print(f"🔊 {text}")

    def say(self, text: str, on_level=None) -> None:
        text = _clean(text)
        if text:
            self.play(text, self.synthesize(text), on_level=on_level)


class SpeechStream:
    """Parle au fil de l'eau : feed() reçoit des morceaux de texte, chaque phrase finie part en lecture."""

    def __init__(self, speaker: Speaker, on_level=None):
        self.speaker = speaker
        self.on_level = on_level
        self.buffer = ""
        self._started = False   # a-t-on déjà commencé à dire la réponse en cours ?
        self._stop = threading.Event()
        self._texts: queue.Queue = queue.Queue()
        self._audios: queue.Queue = queue.Queue(maxsize=2)   # on prépare au plus 2 phrases d'avance
        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop, daemon=True).start()

    # --- côté appelant ---
    def feed(self, piece: str) -> None:
        self.buffer += piece
        ready, self.buffer = split_sentences(self.buffer)
        if not ready and not self._started and len(self.buffer) > 60:
            # Première phrase longue : on commence à parler dès la première virgule, pour réagir vite
            cut = self.buffer.rfind(", ")
            if cut > 25:
                ready, self.buffer = [self.buffer[:cut + 1]], self.buffer[cut + 2:]
        for s in ready:
            self._started = True
            self._put(s)

    def flush(self) -> None:
        """Envoie le reste du texte (fin de réponse)."""
        if self.buffer.strip():
            self._put(self.buffer)
        self.buffer = ""
        self._started = False

    def say(self, text: str) -> None:
        """Dit une phrase complète et attend la fin de la lecture."""
        self.feed(text)
        self.flush()
        self.wait()

    def wait(self) -> None:
        self._texts.join()
        self._audios.join()

    def interrupt(self) -> None:
        """Coupe la parole tout de suite et oublie ce qui restait à dire."""
        self.buffer = ""
        self._started = False
        self._stop.set()
        for q in (self._texts, self._audios):
            try:
                while True:
                    q.get_nowait()
                    q.task_done()
            except queue.Empty:
                pass
        self.wait()
        self._stop.clear()

    # --- fils de travail ---
    def _put(self, text: str) -> None:
        text = _clean(text)
        if text:
            self._texts.put(text)

    def _synth_loop(self) -> None:
        while True:
            text = self._texts.get()
            try:
                if not self._stop.is_set():
                    try:
                        audio = self.speaker.synthesize(text)
                    except Exception as e:
                        print(f"[voix] Synthèse impossible : {e}")
                        audio = None
                    self._audios.put((text, audio))
            finally:
                self._texts.task_done()

    def _play_loop(self) -> None:
        while True:
            text, audio = self._audios.get()
            try:
                if not self._stop.is_set():
                    self.speaker.play(text, audio, on_level=self.on_level, stop=self._stop)
            except Exception as e:
                print(f"[voix] Lecture impossible : {e}")
            finally:
                self._audios.task_done()
