"""Micro et haut-parleur (même code sur les 3 OS grâce à sounddevice)."""
import wave

SR = 16000  # Whisper et openWakeWord travaillent en 16 kHz mono


def record_until_silence(silence_seconds: float = 1.2, max_seconds: float = 20,
                         no_speech_timeout: float = 6.0, stream=None, threshold: float | None = None,
                         prefix=None, already_started: bool = False, on_level=None, stop=None):
    """Enregistre jusqu'à ce que l'utilisateur se taise. Renvoie un tableau float32 (vide si rien dit).

    stream          : flux micro déjà ouvert (float32, 16 kHz) pour ne rien perdre après l'activation
    threshold       : seuil de voix ; calculé sur le bruit ambiant si absent
    prefix          : audio déjà capté à placer au début (ex. la phrase commencée avec « Jarvis »)
    already_started : la personne parle déjà (activation par la voix)
    on_level        : reçoit le volume du micro (0 à 1) tous les 1/10 s, pour l'animation à l'écran
    stop            : threading.Event ; s'il est levé, on arrête d'écouter et on renvoie un audio vide
    """
    import numpy as np
    import sounddevice as sd

    step = 0.1
    block = int(SR * step)

    def _run(s):
        nonlocal threshold
        if threshold is None:
            noise = np.mean([np.sqrt(np.mean(s.read(block)[0] ** 2)) for _ in range(3)])
            threshold = max(noise * 3, 0.01)
        frames = [] if prefix is None else [np.asarray(prefix, dtype="float32").reshape(-1, 1)]
        silent, waited, started = 0.0, 0.0, already_started
        for _ in range(int(max_seconds / step)):
            if stop is not None and stop.is_set():
                return np.array([], dtype="float32")
            data, _ = s.read(block)
            rms = float(np.sqrt(np.mean(data ** 2)))
            frames.append(data.copy())
            if on_level:
                on_level(level_of(rms))
            if rms > threshold:
                started, silent = True, 0.0
            elif started:
                silent += step
                if silent >= silence_seconds:
                    break
            else:
                waited += step
                if waited >= no_speech_timeout:
                    break
        if not started:
            return np.array([], dtype="float32")
        return np.concatenate(frames).flatten()

    if stream is not None:
        return _run(stream)
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=block) as s:
        return _run(s)


def level_of(rms: float) -> float:
    """Volume perçu entre 0 et 1 (échelle logarithmique, comme l'oreille)."""
    import math
    if rms <= 1e-5:
        return 0.0
    return min(1.0, max(0.0, (20 * math.log10(rms) + 50) / 40))   # -50 dB -> 0, -10 dB -> 1


def play_audio(audio, sr: int, on_level=None, stop=None) -> None:
    """Joue un tableau float32 par petits blocs : le volume part vers l'animation, et `stop`
    (threading.Event) permet de couper la parole immédiatement."""
    import numpy as np
    import sounddevice as sd

    block = int(sr * 0.05)
    audio = np.asarray(audio, dtype="float32").reshape(-1)
    with sd.OutputStream(samplerate=sr, channels=1, dtype="float32") as out:
        for i in range(0, len(audio), block):
            if stop is not None and stop.is_set():
                break
            chunk = audio[i:i + block]
            if on_level:
                on_level(level_of(float(np.sqrt(np.mean(chunk ** 2)))))
            out.write(chunk.reshape(-1, 1))
    if on_level:
        on_level(0.0)


def play_wav(path: str) -> None:
    import numpy as np
    import sounddevice as sd

    with wave.open(path, "rb") as wf:
        data = wf.readframes(wf.getnframes())
        audio = np.frombuffer(data, dtype=np.int16)
        if wf.getnchannels() > 1:
            audio = audio.reshape(-1, wf.getnchannels())
        sd.play(audio, wf.getframerate())
        sd.wait()


def beep(freq: float = 880, duration: float = 0.15) -> None:
    """Petit bip pour signaler que Jarvis écoute."""
    try:
        import numpy as np
        import sounddevice as sd

        t = np.linspace(0, duration, int(SR * duration), False)
        sd.play(0.2 * np.sin(2 * np.pi * freq * t), SR)
        sd.wait()
    except Exception:
        print("\a", end="", flush=True)
