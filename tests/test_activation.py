"""Claquements de mains et nettoyage du mot d'activation (sans micro : audio synthétique)."""
import numpy as np

from jarvis.voice.activation import strip_wake_word
from jarvis.voice.clap import ClapDetector

SR, CHUNK = 16000, 1280
STEP = CHUNK / SR
rng = np.random.default_rng(0)


def noise():
    return (rng.normal(0, 0.005, CHUNK)).astype(np.float32)


def clap():
    x = noise()
    t = np.arange(400)
    x[:400] += (0.9 * np.exp(-t / 60) * rng.choice([-1, 1], 400)).astype(np.float32)
    return x


def loud_tone():
    t = np.arange(CHUNK) / SR
    return (0.6 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def feed(detector, chunks):
    """Envoie les blocs avec une horloge simulée ; renvoie True si déclenché."""
    hit = False
    for i, c in enumerate(chunks):
        hit |= detector.process(c, now=i * STEP)
    return hit


def test_double_clap_triggers():
    seq = [noise()] * 20 + [clap()] + [noise()] * 4 + [clap()] + [noise()] * 3
    assert feed(ClapDetector(claps=2), seq)


def test_single_clap_not_enough():
    seq = [noise()] * 20 + [clap()] + [noise()] * 20
    assert not feed(ClapDetector(claps=2), seq)


def test_claps_too_far_apart():
    seq = [noise()] * 20 + [clap()] + [noise()] * 25 + [clap()] + [noise()] * 5   # 2 s d'écart
    assert not feed(ClapDetector(claps=2), seq)


def test_sustained_sound_is_not_a_clap():
    seq = [noise()] * 20 + [loud_tone()] * 6 + [noise()] * 3 + [loud_tone()] * 6 + [noise()] * 3
    assert not feed(ClapDetector(claps=2), seq)


def test_single_clap_mode():
    seq = [noise()] * 20 + [clap()] + [noise()] * 3
    assert feed(ClapDetector(claps=1), seq)


def test_strip_wake_word():
    assert strip_wake_word("Hey Jarvis, ouvre Chrome") == "ouvre Chrome"
    assert strip_wake_word("Jarvis ouvre les paramètres") == "ouvre les paramètres"
    assert strip_wake_word("hé Jarvis !") == ""
    assert strip_wake_word("ouvre le dossier Jarvis") == "ouvre le dossier Jarvis"
    assert strip_wake_word("Hé Jarvie, quelle heure est-il ?") == "quelle heure est-il ?"
    assert strip_wake_word("Djarvis ouvre Chrome") == "ouvre Chrome"
    assert strip_wake_word("Jarvisse") == "Jarvisse"


def test_pick_voice_prefers_france_and_skips_fred():
    from types import SimpleNamespace as V
    from jarvis.voice.tts import pick_voice
    voices = [V(id="com.apple.speech.synthesis.voice.Fred", name="Fred", languages=["en_US"]),
              V(id="com.apple.voice.compact.fr-CA.Amelie", name="Amélie", languages=["fr_CA"]),
              V(id="com.apple.eloquence.fr-FR.Eddy", name="Eddy", languages=["fr_FR"]),
              V(id="com.apple.voice.compact.fr-FR.Thomas", name="Thomas", languages=["fr_FR"])]
    assert pick_voice(voices) == "com.apple.voice.compact.fr-FR.Thomas"
    assert pick_voice(voices, "eddy") == "com.apple.eloquence.fr-FR.Eddy"
    assert pick_voice(voices[:1]) is None
