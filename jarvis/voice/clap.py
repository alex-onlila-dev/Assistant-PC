"""Détection de claquements de mains, en local, sans modèle.

Un claquement = un pic sonore soudain ET très bref.
- soudain : beaucoup plus fort que le bruit de fond de la pièce ;
- bref : le son retombe dès le bloc suivant (la voix ou la musique, elles, durent).
Par défaut il faut 2 claquements rapprochés, pour éviter les déclenchements accidentels.
"""
import time

import numpy as np


class ClapDetector:
    def __init__(self, claps: int = 2, sensitivity: float = 0.5,
                 min_gap: float = 0.12, max_gap: float = 0.8):
        sensitivity = min(max(sensitivity, 0.0), 1.0)
        self.claps_needed = max(1, claps)
        self.ratio = 4 + (1 - sensitivity) * 8          # pic / bruit de fond : 12 (peu sensible) à 4 (très sensible)
        self.min_peak = 0.25 + (1 - sensitivity) * 0.35  # amplitude minimale (0 à 1)
        self.min_gap = min_gap                            # écart mini entre deux claquements (s)
        self.max_gap = max_gap                            # écart maxi entre deux claquements (s)
        self.background = 0.01
        self.candidate: tuple[float, float] | None = None  # (instant, rms) d'un pic à confirmer
        self.claps: list[float] = []
        self.last_spike = -1.0
        self.prev_loud = False

    def process(self, chunk: np.ndarray, now: float | None = None) -> bool:
        """Analyse un bloc audio (int16 ou float32). Renvoie True quand la série de claquements est complète."""
        now = time.monotonic() if now is None else now
        x = chunk.astype(np.float32)
        if chunk.dtype == np.int16:
            x /= 32768.0
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        rms = float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
        triggered = False

        # 1. Confirmer le pic du bloc précédent : le son doit être retombé
        if self.candidate is not None:
            t, crms = self.candidate
            self.candidate = None
            if rms < crms * 0.5:
                triggered = self._register(t)

        # 2. Chercher un nouveau pic soudain
        spike = peak >= self.min_peak and rms > self.background * self.ratio
        if spike and not self.prev_loud and now - self.last_spike >= self.min_gap:
            self.candidate = (now, rms)
            self.last_spike = now
        if not spike:
            self.background = max(0.002, 0.95 * self.background + 0.05 * rms)
        self.prev_loud = spike

        # 3. Oublier une série trop ancienne
        if self.claps and now - self.claps[-1] > self.max_gap and self.candidate is None:
            self.claps = []
        return triggered

    def _register(self, t: float) -> bool:
        if self.claps and t - self.claps[-1] > self.max_gap:
            self.claps = []
        self.claps.append(t)
        if len(self.claps) >= self.claps_needed:
            self.claps = []
            return True
        return False
