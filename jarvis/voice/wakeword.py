"""Appel par la voix, détecté en local avec openWakeWord.

wake_word peut être :
- un modèle intégré, ex. "hey_jarvis" (fonctionne tout de suite) ;
- le chemin d'un modèle personnalisé .onnx, ex. "models/jarvis.onnx",
  pour réagir à « Jarvis » tout seul (voir README, section Activation).
"""
from pathlib import Path

import numpy as np

CHUNK = 1280  # 80 ms à 16 kHz, taille attendue par openWakeWord


class WakeWordDetector:
    def __init__(self, wake_word: str = "hey_jarvis", threshold: float = 0.5):
        import openwakeword
        from openwakeword.model import Model

        is_file = wake_word.endswith(".onnx") or wake_word.endswith(".tflite")
        if is_file:
            from jarvis.config import ROOT
            path = Path(wake_word).expanduser()
            if not path.is_absolute():
                path = ROOT / path
            if not path.exists():
                raise FileNotFoundError(f"Modèle de mot d'activation introuvable : {path}")
            self.key = path.stem
            models = [str(path)]
        else:
            try:
                openwakeword.utils.download_models(model_names=[wake_word])
            except Exception:
                pass  # déjà téléchargé ou hors ligne
            self.key = wake_word
            models = [wake_word]
        self.threshold = threshold
        self.model = Model(wakeword_models=models, inference_framework="onnx")

    def process(self, chunk: np.ndarray) -> bool:
        """Analyse un bloc int16 de 1280 échantillons. True si le mot d'activation est entendu."""
        scores = self.model.predict(chunk)
        if any(self.key in name and score >= self.threshold for name, score in scores.items()):
            self.model.reset()
            return True
        return False
