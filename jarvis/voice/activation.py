"""Activation de Jarvis : par la voix (« Jarvis… ») ou par claquement de mains.

Les deux écoutent en même temps sur le même micro.
- Voix  : la phrase dite d'une traite est captée (« Jarvis, ouvre les paramètres »),
          grâce à une mémoire tampon des dernières secondes.
- Clap  : un bip retentit, puis Jarvis écoute la phrase.
"""
import re
from collections import deque

from jarvis.voice.audio_io import SR, beep, record_until_silence
from jarvis.voice.wakeword import CHUNK

# Whisper en français écrit aussi « Jarvie », « Jarvi », « Djarvis »…
_WAKE_PREFIX = re.compile(r"^\W*(?:(?:h[eéèê]y?|eh|ok|dis)\W+)?d?jarv(?:is|ice|ie|y|i)\b\W*", re.IGNORECASE)


def strip_wake_word(text: str) -> str:
    """« Hey Jarvis, ouvre Chrome » -> « ouvre Chrome »."""
    return _WAKE_PREFIX.sub("", (text or "").strip()).strip()


class ActivationListener:
    def __init__(self, cfg: dict):
        a = cfg.get("activation", {})
        v = cfg.get("voice", {})
        modes = [m.lower() for m in a.get("modes", ["voix", "clap"])]
        self.silence = v.get("silence_seconds", 1.2)
        self.max_record = v.get("max_record_seconds", 20)
        self.preroll_seconds = a.get("preroll_seconds", 1.5)

        self.wake = None
        if "voix" in modes:
            from jarvis.voice.wakeword import WakeWordDetector
            self.wake = WakeWordDetector(v.get("wake_word", "hey_jarvis"), v.get("wake_threshold", 0.5))

        self.clap = None
        if "clap" in modes:
            from jarvis.voice.clap import ClapDetector
            self.clap = ClapDetector(a.get("claps", 2), a.get("clap_sensitivity", 0.5))

        if not self.wake and not self.clap:
            raise ValueError("Aucun mode d'activation : mets 'voix' et/ou 'clap' dans activation.modes.")

    def describe(self) -> str:
        parts = []
        if self.wake:
            parts.append(f"dis « {self.wake.key.replace('_', ' ')} »")
        if self.clap:
            n = self.clap.claps_needed
            parts.append(f"claque {n} fois des mains" if n > 1 else "claque des mains")
        return " ou ".join(parts)

    def listen(self, on_wake=None, on_level=None, stop=None):
        """Attend une activation, puis enregistre la commande.

        on_wake(mode) est appelé dès l'activation, avant l'enregistrement : l'écran réagit tout de suite.
        Renvoie (mode, audio float32 16 kHz) où mode vaut "voix" ou "clap" ; (None, None) si `stop` est levé.
        """
        import numpy as np
        import sounddevice as sd

        buffer: deque = deque(maxlen=max(1, int(self.preroll_seconds * SR / CHUNK)))
        noise = 0.01
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=CHUNK) as stream:
            while not (stop is not None and stop.is_set()):
                data, _ = stream.read(CHUNK)
                chunk = data.flatten()
                buffer.append(chunk.copy())
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                if rms < noise * 3:
                    noise = max(0.002, 0.97 * noise + 0.03 * rms)
                pcm16 = (np.clip(chunk, -1, 1) * 32767).astype(np.int16)

                if self.wake and self.wake.process(pcm16):
                    if on_wake:
                        on_wake("voix")
                    audio = record_until_silence(self.silence, self.max_record, stream=stream,
                                                 threshold=max(noise * 3, 0.01),
                                                 prefix=np.concatenate(buffer), already_started=True,
                                                 on_level=on_level)
                    return "voix", audio

                if self.clap and self.clap.process(chunk):
                    if on_wake:
                        on_wake("clap")
                    beep()
                    audio = record_until_silence(self.silence, self.max_record, stream=stream,
                                                 threshold=max(noise * 3, 0.01), on_level=on_level)
                    return "clap", audio
        return None, None
