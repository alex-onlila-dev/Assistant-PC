# Jarvis — assistant personnel local

Assistant personnel qui tourne sur ton ordinateur. Son cerveau est au choix : un modèle **local** (Ollama, rien ne
quitte la machine) ou un service **en ligne** — Claude, ou tout service compatible OpenAI — quand le PC est trop
modeste pour Ollama ou qu'on ne veut rien installer.
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
  Cerveau         Outils          Confirmation
(Ollama, Claude  fichiers, analyse,  (oui / non)
 ou autre)       apps, alarmes…
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
│   ├── config.py            chargement et enregistrement de la configuration
│   ├── autostart.py         lancement automatique à l'ouverture de session
│   ├── core/                le cerveau (identique sur tous les OS)
│   │   ├── agent.py         boucle agent + blocage des actions non confirmées
│   │   ├── llm/             le cerveau, interchangeable
│   │   │   ├── ollama.py         modèle local
│   │   │   ├── claude.py         Claude (API Anthropic)
│   │   │   └── openai_compat.py  OpenAI, Mistral, Groq, OpenRouter, Gemini, LM Studio…
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
│       ├── gui.py           fenêtre de discussion façon ChatGPT/Claude + icône barre système (PySide6)
│       ├── settings.py      fenêtre Paramètres : tous les réglages, téléchargement de modèles
│       └── widgets.py       composants partagés
└── tests/                   tests de la règle de confirmation, des analyseurs, etc.
```

## 2. Stack

| Brique | Choix |
|---|---|
| Langage | Python 3.11 (3.12 possible sur macOS et Windows) |
| Cerveau | Local via Ollama (`qwen2.5:7b`, vision `qwen2.5vl:7b`), ou Claude (`claude-opus-5-5`), ou un service compatible OpenAI |
| Écoute | faster-whisper |
| Mot d'activation | openWakeWord (« Hey Jarvis ») |
| Parole | Piper (repli : pyttsx3) |
| Fichiers | pathlib, send2trash, filetype |
| Analyse | PyMuPDF, python-docx, openpyxl, python-pptx, Pillow, ffmpeg |
| Alarmes | APScheduler, plyer |
| Interface | PySide6 |
| Mémoire | SQLite |

## 3. Installation

### Installation en un clic (recommandée)

| Système | Comment |
|---|---|
| **Windows 10/11** | Télécharge `JarvisSetup-x.y.z.exe` dans les *Releases* du dépôt et lance-le. |
| **macOS** | Dans le dossier du projet : `./installers/install.sh` |
| **Linux** | Dans le dossier du projet : `./installers/install.sh` (demande ton mot de passe pour portaudio, ffmpeg…) |

L'installateur fait tout :
- il te demande quel cerveau utiliser : **Ollama** (local), **Claude** (clé API), **un autre service** compatible OpenAI,
  ou **plus tard** (dans Paramètres > Cerveau). Ollama n'est téléchargé que si tu le choisis, avec un modèle adapté
  à ta mémoire vive (`qwen2.5:3b` sous 12 Go, sinon `qwen2.5:7b`) ;
- il installe Python 3.11 (via `uv`, sans toucher au Python du système) et les modules ;
- il précharge Whisper, la voix française et « Hey Jarvis » ;
- il crée l'application (`Jarvis.app` sur Mac, menu Démarrer sur Windows, menu des applications sur Linux),
  la commande `jarvis` et le lancement automatique à l'ouverture de session.

**Pas de droits administrateur.** Jarvis s'installe pour ton compte et accède à tout ce que tu peux ouvrir toi-même.
L'installer « à la racine » ne lui donnerait rien de plus d'utile, mais lui permettrait de modifier le système :
une erreur du modèle pourrait alors casser la machine. Ce qui débloque vraiment l'accès, ce sont les autorisations :
- **macOS** : *Réglages Système > Confidentialité et sécurité > Accès complet au disque > Jarvis* (Documents, Bureau, iCloud…),
  et le micro (demandé au premier lancement) ;
- **Windows** : *Paramètres > Confidentialité > Microphone > Autoriser les applications de bureau*.

| | macOS | Linux | Windows |
|---|---|---|---|
| Programme | `~/Library/Application Support/Jarvis/app` | `~/.local/share/jarvis/app` | `%LOCALAPPDATA%\Jarvis\app` |
| Configuration, historique, journal | `~/.jarvis/` | `~/.jarvis/` | `%USERPROFILE%\.jarvis\` |

Relancer l'installateur met Jarvis à jour en gardant ta configuration (`~/.jarvis/config.yaml`).
Tous les réglages se changent aussi dans la fenêtre : **⚙ Paramètres** en bas de la barre latérale (ou Ctrl+,).
Options : `--brain ollama|claude|openai|later`, `--base-url URL`, `--api-model NOM`, `--no-autostart`,
`--model qwen2.5:7b`, `--with-vision`, `--yes` (Windows : `-Brain`, `-BaseUrl`, `-ApiModel`, `-KeyFile`, `-NoAutostart`,
`-Model`, `-WithVision`, `-Yes`). Sans question (`--yes`), le cerveau se choisit plus tard dans les Paramètres.
La clé API se donne par la variable `JARVIS_API_KEY` (ou `-KeyFile` sous Windows), jamais sur la ligne de commande.
Désinstaller : `installers/uninstall.sh` (Windows : *Paramètres > Applications > Jarvis*).

**Publier une version Windows** : `git tag v1.0.0 && git push --tags`. GitHub Actions teste l'installation sur Linux
et Windows, construit `JarvisSetup-1.0.0.exe` et le joint à la Release.

### Installation manuelle (développement)

#### a. Ollama (le cerveau)
Télécharge Ollama sur https://ollama.com puis :
```bash
ollama pull qwen2.5:7b      # cerveau principal (gère les outils)
ollama pull qwen2.5vl:7b    # vision : images, PDF scannés, vidéos
```
Machine modeste (8 Go de RAM) : prends `qwen2.5:3b` et `llava:7b`, et adapte `config.yaml`.

#### b. ffmpeg (pour l'analyse vidéo)
- Windows : `winget install ffmpeg`
- macOS : `brew install ffmpeg`
- Linux : `sudo apt install ffmpeg`

#### c. Dépendances Python
```bash
python -m venv .venv
# Windows : .venv\Scripts\activate     macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
```
Linux : installe aussi `sudo apt install libportaudio2 libnotify-bin espeak-ng`.

#### d. Voix française naturelle (optionnel)
Télécharge une voix Piper française (ex. `fr_FR-siwis-medium.onnx` et son `.onnx.json`)
depuis le dépôt de voix Piper, place-les dans `models/`, puis dans `config.yaml` :
```yaml
voice:
  piper_model: "models/fr_FR-siwis-medium.onnx"
```

### Choisir le cerveau

Dans **⚙ Paramètres > Cerveau** (bouton « Tester le cerveau » pour vérifier avant d'enregistrer), ou `llm.provider` dans `config.yaml` :

| Choix | Ce qu'il faut | À savoir |
|---|---|---|
| `auto` (défaut) | — | Ollama s'il est installé, sinon Claude ou l'autre service si leur clé est renseignée |
| `ollama` | Ollama et un modèle (plusieurs Go) | Rien ne quitte l'ordinateur ; lent sur une petite machine |
| `claude` | Une clé API créée sur [console.anthropic.com](https://console.anthropic.com) | Payée à l'usage. Un abonnement Claude Pro/Max ne sert pas ici : il ne fonctionne que dans les applications Claude |
| `openai` | L'adresse du service, sa clé et le nom du modèle | OpenAI, Mistral, Groq, OpenRouter, DeepSeek, Gemini, ou LM Studio en local |

Avec un service en ligne, tes demandes **et le contenu des fichiers que Jarvis lit** sont envoyés à ce service.
La règle de confirmation ne change pas : c'est Jarvis qui l'applique, quel que soit le cerveau.
Les clés sont enregistrées dans `~/.jarvis/config.yaml` ; pour Claude, la variable `ANTHROPIC_API_KEY` marche aussi.

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
