"""Voix -> texte, en local avec faster-whisper."""
import threading

_instance = None
_lock = threading.Lock()


class Transcriber:
    def __init__(self, model_size: str = "small", device: str = "auto", language: str = "fr"):
        from faster_whisper import WhisperModel

        self.language = language
        self.model = WhisperModel(model_size, device=device, compute_type="int8")

    def _join(self, segments) -> str:
        return " ".join(s.text.strip() for s in segments).strip()

    def transcribe_array(self, audio, language: str | None = None) -> str:
        """Pour les commandes vocales (audio float32 16 kHz)."""
        if audio is None or len(audio) == 0:
            return ""
        # Commande courte : décodage glouton (beam_size=1) et sans contexte précédent = bien plus rapide
        segments, _ = self.model.transcribe(audio, language=language or self.language, vad_filter=True,
                                            beam_size=1, condition_on_previous_text=False)
        return self._join(segments)

    def transcribe_file(self, path: str) -> tuple[str, dict]:
        """Pour l'analyse de fichiers audio/vidéo (langue détectée automatiquement)."""
        segments, info = self.model.transcribe(path, vad_filter=True)
        text = self._join(segments)
        return text, {"duration": info.duration, "language": info.language}


def get_transcriber(cfg: dict) -> Transcriber:
    """Le modèle est lourd : on le charge une seule fois."""
    global _instance
    with _lock:
        if _instance is None:
            v = cfg.get("voice", {})
            _instance = Transcriber(v.get("whisper_model", "small"), v.get("whisper_device", "auto"),
                                    cfg.get("assistant", {}).get("language", "fr"))
    return _instance
