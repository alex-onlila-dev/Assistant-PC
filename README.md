# Jarvis — assistant personnel local

Assistant personnel qui tourne **entièrement sur ton ordinateur**, sans API externe.
Il lit, analyse et gère tes fichiers, ouvre tes applications et tes paramètres, règle des alarmes,
et donne un avis impartial sur tes projets. Il fonctionne à la voix, en texte ou en fenêtre.

**Règle d'or : il lit librement, il confirme avant tout le reste.**
Toute action qui modifie quelque chose (créer, modifier, déplacer, supprimer, ouvrir, lancer, régler)
attend ton « oui ». Si tu refuses, il annule. Les suppressions vont toujours à la corbeille.

---

## 1. Architecture

À retenir : **un seul cerveau, trois adaptateurs.**

```
Voix / Texte / Fenêtre          (interfaces)
        │
   Boucle agent                 penser → agir → observer → recommencer
        │
 ┌──────┼───────────────┬──────────────┐
Cerveau local     Outils          Confirmation
(Ollama)     fichiers, analyse,   (oui / non)
             apps, alarmes…
                   │
          Adaptateur OS  →  Windows | macOS | Linux
```

```
jarvis-assistant/
├── main.py                  point d'entrée (--cli, --voice, fenêtre par défaut)
├── config.yaml              modèles, voix, sécurité, limites
├── requirements.txt
├── jarvis/
│   ├── bootstrap.py         assemble toutes les briques
│   ├── config.py
│   ├── core/                le cerveau (identique sur tous les OS)
│   │   ├── agent.py         boucle agent + blocage des actions non confirmées
│   │   ├── llm.py           client Ollama (local)
│   │   ├── tools.py         registre des outils (confirm=True/False)
│   │   ├── confirmation.py  confirmation texte, compréhension de « oui / non »
│   │   ├── prompts.py       consignes données au cerveau (dont l'impartialité)
│   │   ├── memory.py        historique et alarmes (SQLite)
│   │   ├── alarms.py        alarmes et minuteurs gérés par Jarvis
│   │   └── context.py       contexte partagé par les outils
│   ├── tools/               ce que Jarvis sait faire
│   │   ├── files.py         lire, lister, chercher, créer, modifier, déplacer, copier, supprimer, ouvrir
│   │   ├── analysis.py      analyser n'importe quel fichier
│   │   ├── system.py        applications, paramètres, web, état de la machine
│   │   ├── alarms.py        alarmes, minuteurs
│   │   └── project.py       lecture d'un projet entier pour un avis
│   ├── analyzers/           un analyseur par type de fichier
│   │   ├── text.py  pdf.py  image.py  audio.py  video.py
│   │   └── office.py  archive.py  binary.py
│   ├── os_adapters/         le « corps » : une implémentation par OS
│   │   ├── base.py          interface commune
│   │   ├── windows.py  macos.py  linux.py
│   ├── voice/               voix
│   │   ├── activation.py    réveil par la voix OU par claquement de mains
│   │   ├── clap.py          détection des claquements de mains
│   │   ├── wakeword.py      appel par le nom (openWakeWord)
│   │   ├── stt.py           voix → texte (faster-whisper)
│   │   ├── tts.py           texte → voix (Piper, sinon voix système)
│   │   ├── audio_io.py      micro, haut-parleur, bip
│   │   └── loop.py          mode vocal + confirmation à la voix
│   └── ui/
│       ├── cli.py           mode terminal
│       └── gui.py           fenêtre + icône barre système (PySide6)
└── tests/                   tests de la règle de confirmation, des analyseurs, etc.
```

## 2. Stack

| Brique | Choix |
|---|---|
| Langage | Python 3.11+ |
| Cerveau | Modèle local via Ollama (`qwen2.5:7b`), vision : `qwen2.5vl:7b` |
| Écoute | faster-whisper |
| Mot d'activation | openWakeWord (« Hey Jarvis ») |
| Parole | Piper (repli : pyttsx3) |
| Fichiers | pathlib, send2trash, filetype |
| Analyse | PyMuPDF, python-docx, openpyxl, python-pptx, Pillow, ffmpeg |
| Alarmes | APScheduler, plyer |
| Interface | PySide6 |
| Mémoire | SQLite |

## 3. Installation

### a. Ollama (le cerveau)
Télécharge Ollama sur https://ollama.com puis :
```bash
ollama pull qwen2.5:7b      # cerveau principal (gère les outils)
ollama pull qwen2.5vl:7b    # vision : images, PDF scannés, vidéos
```
Machine modeste (8 Go de RAM) : prends `qwen2.5:3b` et `llava:7b`, et adapte `config.yaml`.

### b. ffmpeg (pour l'analyse vidéo)
- Windows : `winget install ffmpeg`
- macOS : `brew install ffmpeg`
- Linux : `sudo apt install ffmpeg`

### c. Dépendances Python
```bash
python -m venv .venv
# Windows : .venv\Scripts\activate     macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
```
Linux : installe aussi `sudo apt install libportaudio2 libnotify-bin espeak-ng`.

### d. Voix française naturelle (optionnel)
Télécharge une voix Piper française (ex. `fr_FR-siwis-medium.onnx` et son `.onnx.json`)
depuis le dépôt de voix Piper, place-les dans `models/`, puis dans `config.yaml` :
```yaml
voice:
  piper_model: "models/fr_FR-siwis-medium.onnx"
```

## 4. Lancement

```bash
python main.py           # fenêtre + icône dans la barre système
python main.py --cli     # mode texte
python main.py --voice   # mode vocal avec la bulle à l'écran : appelle-le ou claque des mains
python main.py --voice --console   # mode vocal dans le terminal, sans bulle
```

### La bulle vocale

En mode `--voice`, Jarvis vit dans la barre des menus. Quand tu l'appelles, une bulle apparaît en bas de l'écran :

| Orbe | État |
|---|---|
| Bleu, qui respire avec ta voix | il t'écoute |
| Cerveau 🧠 entouré de points qui tournent | il réfléchit (avec « Je cherche tes fichiers… » quand il utilise un outil) |
| Barres roses qui suivent sa voix | il parle ; sa réponse s'affiche en même temps |
| Ambré, avec « ? » | il attend ta confirmation (oui / non) |

**C'est une conversation, comme un appel** : après sa réponse, il t'écoute à nouveau, sans mot d'activation.
La conversation se termine :
- quand tu dis « c'est tout », « on s'arrête là », « c'est bon », « merci », « au revoir »… ;
- après 8 secondes de silence (`voice.followup_seconds`) ;
- si tu touches la bulle (ça lui coupe aussi la parole).

Il retourne alors en veille. « Éteins-toi » ou le menu « Quitter Jarvis » l'arrêtent complètement.
Le menu « Parler à Jarvis » ouvre une conversation sans mot d'activation.

**Réactivité** : Jarvis commence à parler dès que sa première phrase est prête, sans attendre la fin de sa réponse.
Au lancement, il fait lire ses consignes au cerveau (environ 30 s sur un Mac 8 Go) : ensuite, la première parole
arrive en 2 à 3 s pour une question simple, 5 à 7 s quand il doit utiliser un outil.

### Activation en mode vocal

Deux façons de réveiller Jarvis, actives en même temps :

| Mode | Comment | Ce qui se passe |
|---|---|---|
| **Voix** | « Hey Jarvis, ouvre les paramètres Bluetooth » | La phrase dite d'une traite est captée en entier. Si tu dis juste « Hey Jarvis », il répond « Oui ? » et t'écoute. |
| **Clap** | Clap-clap, puis ta phrase | Un bip retentit, puis il écoute ta phrase. |

Réglages dans `config.yaml`, section `activation` :
- `modes` : `["voix", "clap"]`, `["voix"]` ou `["clap"]`.
- `claps` : 2 par défaut. Un seul claquement réagit plus vite mais déclenche plus souvent par erreur (porte qui claque, objet qui tombe).
- `clap_sensitivity` : baisse-la si la pièce est bruyante, monte-la si Jarvis ne t'entend pas.

**Répondre à « Jarvis » tout seul (sans « Hey »)** : le modèle intégré est entraîné sur « Hey Jarvis ».
Pour le seul mot « Jarvis », entraîne un modèle personnalisé avec l'outil d'entraînement d'openWakeWord
(il génère des voix synthétiques, pas besoin d'enregistrer des centaines d'échantillons),
place le fichier dans `models/jarvis.onnx`, puis :
```yaml
voice:
  wake_word: "models/jarvis.onnx"
```

Exemples :
- « Lis-moi le fichier notes.txt sur le bureau »
- « Cherche tous mes PDF qui parlent de facture »
- « Analyse la vidéo reunion.mp4 dans Téléchargements et fais-moi un résumé »
- « Donne-moi ton avis sur le projet dans Documents/WortisERP »
- « Supprime le fichier brouillon.docx » → il le trouve, te demande, puis corbeille
- « Ouvre les paramètres Bluetooth »
- « Réveille-moi à 6h30 »

## 5. Tests
```bash
pytest
```

## 6. Ajouter une capacité

**Un nouvel outil** : dans `jarvis/tools/`, une fonction décorée suffit.
```python
@registry.register("nom_outil", "Ce que fait l'outil.",
                   {"x": param("string", "description")}, ["x"],
                   confirm=True, summary=lambda a: f"Faire telle chose avec {a['x']}")
def nom_outil(x: str) -> str:
    ...
```
`confirm=True` pour tout ce qui modifie quelque chose.

**Un nouvel OS** : une classe dans `jarvis/os_adapters/` qui hérite de `OSAdapter`.

## 7. Pistes pour la suite
- Contrôle fin des applications (cliquer, taper) : `pywinauto` (Windows), AppleScript (macOS), `xdotool` (Linux).
- Volume, luminosité, Wi-Fi on/off par adaptateur OS.
- Mémoire à long terme (préférences, faits importants) dans SQLite.
- Recherche dans le contenu des fichiers (index plein texte).
- Exécutables autonomes avec PyInstaller, un par OS.
