#!/usr/bin/env bash
# ============================================================
#  Installation de Jarvis — macOS et Linux
#
#  ./installers/install.sh            installation guidée
#  ./installers/install.sh --yes      sans questions (réponses par défaut)
#
#  Options : --no-autostart   ne pas lancer Jarvis à l'ouverture de session
#            --skip-ollama    ne pas installer Ollama ni télécharger le cerveau
#            --skip-models    ne pas précharger Whisper / la voix / le mot d'activation
#            --model NOM      modèle Ollama à utiliser (défaut : choisi selon la mémoire vive)
#            --with-vision    télécharger aussi le modèle vision (images, vidéos ; ~6 Go)
#
#  Jarvis s'installe pour ton compte, sans droits administrateur : il a accès à tout ce que
#  tu peux ouvrir toi-même. Relancer ce script met Jarvis à jour en gardant ta configuration.
# ============================================================
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="$(uname -s)"
YES=0; AUTOSTART=1; SKIP_OLLAMA=0; SKIP_MODELS=0; MODEL=""; VISION=0

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --no-autostart) AUTOSTART=0 ;;
    --skip-ollama) SKIP_OLLAMA=1 ;;
    --skip-models) SKIP_MODELS=1 ;;
    --model) MODEL="$2"; shift ;;
    --with-vision) VISION=1 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1"; exit 1 ;;
  esac
  shift
done

# --- Emplacements (modifiables par variables d'environnement, utile pour tester) ---
if [ "$OS" = "Darwin" ]; then
  APP_DIR="${JARVIS_APP_DIR:-$HOME/Library/Application Support/Jarvis/app}"
  MAC_APP="${JARVIS_MAC_APP:-$HOME/Applications/Jarvis.app}"
elif [ "$OS" = "Linux" ]; then
  APP_DIR="${JARVIS_APP_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/jarvis/app}"
else
  echo "Système non pris en charge par ce script ($OS). Sous Windows, utilise JarvisSetup.exe."; exit 1
fi
BIN_DIR="${JARVIS_BIN_DIR:-$HOME/.local/bin}"
DATA_DIR="${JARVIS_HOME:-$HOME/.jarvis}"
PIPER_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium"

# --- Affichage ---
bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
ask()  {   # ask "question" -> vrai si oui (oui par défaut)
  [ "$YES" = 1 ] && return 0
  printf '  %s [O/n] ' "$1"; read -r r </dev/tty || r=""
  case "$r" in n|N|non|Non|NON) return 1 ;; *) return 0 ;; esac
}
have() { command -v "$1" >/dev/null 2>&1; }

# --- Mémoire vive -> taille du cerveau ---
if [ "$OS" = "Darwin" ]; then
  RAM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
else
  RAM_GB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
fi
if [ -z "$MODEL" ]; then
  if [ "$RAM_GB" -lt 12 ]; then MODEL="qwen2.5:3b"; else MODEL="qwen2.5:7b"; fi
fi

bold "Installation de Jarvis"
echo "  Système        : $OS ($(uname -m)), ${RAM_GB} Go de mémoire vive"
echo "  Programme      : $APP_DIR"
echo "  Commande       : $BIN_DIR/jarvis"
[ "$OS" = "Darwin" ] && echo "  Application    : $MAC_APP"
echo "  Configuration  : $DATA_DIR/config.yaml (conservée lors des mises à jour)"
echo "  Cerveau        : $MODEL$([ "$SKIP_OLLAMA" = 1 ] && echo ' (non installé : --skip-ollama)')"
echo "  Démarrage auto : $([ "$AUTOSTART" = 1 ] && echo oui || echo non)"
ask "Continuer ?" || { echo "Installation annulée."; exit 0; }

# ------------------------------------------------------------ 1. dépendances système
step "Dépendances système"
if [ "$OS" = "Linux" ]; then
  PKGS=""
  if have apt-get; then
    PKGS="libportaudio2 ffmpeg espeak-ng libnotify-bin libxcb-cursor0 libegl1 curl"
    INSTALL="sudo apt-get install -y $PKGS"; PRE="sudo apt-get update"
  elif have dnf; then
    PKGS="portaudio ffmpeg-free espeak-ng libnotify xcb-util-cursor curl"
    INSTALL="sudo dnf install -y $PKGS"; PRE="true"
  elif have pacman; then
    PKGS="portaudio ffmpeg espeak-ng libnotify xcb-util-cursor curl"
    INSTALL="sudo pacman -S --needed --noconfirm $PKGS"; PRE="true"
  fi
  if [ -n "$PKGS" ]; then
    echo "  Paquets nécessaires (micro, vidéo, notifications, fenêtre) : $PKGS"
    if ask "Les installer maintenant (demande ton mot de passe administrateur) ?"; then
      $PRE && $INSTALL && ok "paquets installés" || warn "échec : installe-les à la main puis relance"
    else
      warn "ignoré : le micro ou la bulle risquent de ne pas marcher"
    fi
  else
    warn "gestionnaire de paquets non reconnu : installe portaudio, ffmpeg et espeak-ng à la main"
  fi
else
  if have ffmpeg; then ok "ffmpeg déjà présent"
  elif have brew; then
    if ask "Installer ffmpeg (analyse des vidéos) avec Homebrew ?"; then brew install ffmpeg && ok "ffmpeg installé"; fi
  else
    warn "ffmpeg absent (analyse vidéo indisponible). Installe Homebrew puis : brew install ffmpeg"
  fi
fi

# ------------------------------------------------------------ 2. uv (fournit Python, sans toucher au Python du système)
step "Python"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! have uv; then
  echo "  Installation de uv (gestionnaire Python autonome, dans ~/.local/bin)…"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
have uv || { echo "uv introuvable après installation."; exit 1; }
ok "uv $(uv --version | awk '{print $2}')"

# ------------------------------------------------------------ 3. copie du programme
step "Programme"
mkdir -p "$APP_DIR" "$BIN_DIR" "$DATA_DIR"
if [ "$(cd "$APP_DIR" && pwd)" != "$SRC" ]; then
  # On copie le code ; on garde le .venv et les modèles déjà téléchargés (mise à jour rapide)
  (cd "$SRC" && tar --exclude ./.git --exclude ./.venv --exclude ./models --exclude '*/__pycache__' \
      --exclude ./.pytest_cache -cf - .) | (cd "$APP_DIR" && tar -xf -)
  if [ -d "$SRC/models" ]; then mkdir -p "$APP_DIR/models" && cp -n "$SRC/models/"* "$APP_DIR/models/" 2>/dev/null || true; fi
fi
ok "code copié dans $APP_DIR"

# Python 3.11 : openwakeword a besoin de tflite-runtime sous Linux, qui n'existe pas en 3.12
# Un environnement d'une autre version (ancienne installation) est recréé, pas mélangé
if [ -f "$APP_DIR/.venv/pyvenv.cfg" ] && ! grep -q '^version_info = 3\.11' "$APP_DIR/.venv/pyvenv.cfg"; then
  rm -rf "$APP_DIR/.venv"
fi
uv venv --quiet --allow-existing --python 3.11 "$APP_DIR/.venv"
echo "  Installation des modules Python (quelques minutes la première fois)…"
uv pip install --quiet --python "$APP_DIR/.venv/bin/python" -r "$APP_DIR/requirements.txt"
PY="$APP_DIR/.venv/bin/python"
ok "Python $("$PY" -c 'import sys; print(sys.version.split()[0])') et modules installés"

# ------------------------------------------------------------ 4. configuration de l'utilisateur
step "Configuration"
if [ -f "$DATA_DIR/config.yaml" ]; then
  ok "configuration existante conservée ($DATA_DIR/config.yaml)"
else
  sed -e "s|^  model: \"[^\"]*\"|  model: \"$MODEL\"|" "$APP_DIR/config.yaml" > "$DATA_DIR/config.yaml"
  ok "configuration créée ($DATA_DIR/config.yaml, cerveau : $MODEL)"
fi

# ------------------------------------------------------------ 5. voix et écoute
if [ "$SKIP_MODELS" = 0 ]; then
  step "Voix et écoute"
  mkdir -p "$APP_DIR/models"
  if [ ! -f "$APP_DIR/models/fr_FR-siwis-medium.onnx" ]; then
    echo "  Téléchargement de la voix française (60 Mo)…"
    curl -fsSL -o "$APP_DIR/models/fr_FR-siwis-medium.onnx" "$PIPER_URL/fr_FR-siwis-medium.onnx"
    curl -fsSL -o "$APP_DIR/models/fr_FR-siwis-medium.onnx.json" "$PIPER_URL/fr_FR-siwis-medium.onnx.json"
  fi
  ok "voix française (Piper)"
  echo "  Préchargement de la reconnaissance vocale et du mot d'activation…"
  # Pas de heredoc dans un « ( … ) » : le bash 3.2 de macOS relit ensuite ces lignes comme du shell
  PRELOAD='from jarvis.config import load_config
cfg = load_config()
from jarvis.voice.stt import get_transcriber
get_transcriber(cfg)
import openwakeword
openwakeword.utils.download_models(model_names=[cfg["voice"]["wake_word"]])'
  if (cd "$APP_DIR" && "$PY" -c "$PRELOAD") 2>/dev/null; then
    ok "Whisper et « Hey Jarvis » prêts"
  else
    warn "préchargement impossible (pas de réseau ?) : ils se téléchargeront au premier lancement"
  fi
fi

# ------------------------------------------------------------ 6. le cerveau (Ollama)
if [ "$SKIP_OLLAMA" = 0 ]; then
  step "Cerveau (Ollama)"
  if ! have ollama; then
    if [ "$OS" = "Darwin" ]; then
      if have brew && ask "Installer Ollama avec Homebrew ?"; then
        brew install ollama && brew services start ollama
      else
        warn "Installe Ollama depuis https://ollama.com/download puis relance ce script."; open "https://ollama.com/download" || true
      fi
    else
      if ask "Installer Ollama (script officiel, demande ton mot de passe administrateur) ?"; then
        curl -fsSL https://ollama.com/install.sh | sh
      fi
    fi
  fi
  if have ollama; then
    if ! curl -s -m 2 http://localhost:11434/api/tags >/dev/null; then
      (nohup ollama serve >/dev/null 2>&1 &) ; sleep 3
    fi
    echo "  Téléchargement du cerveau $MODEL (plusieurs Go la première fois)…"
    ollama pull "$MODEL" && ok "cerveau $MODEL prêt"
    if [ "$VISION" = 1 ]; then ollama pull qwen2.5vl:7b && ok "modèle vision prêt"; fi
  else
    warn "Ollama absent : Jarvis ne pourra pas réfléchir tant qu'il n'est pas installé."
  fi
fi

# ------------------------------------------------------------ 7. lanceurs
step "Lanceurs"
cat > "$BIN_DIR/jarvis" <<EOF
#!/usr/bin/env bash
# Lanceur de Jarvis. Sans option : la bulle vocale. « jarvis --cli » : mode texte.
cd "$APP_DIR"
if [ \$# -eq 0 ]; then set -- --voice; fi
exec "$PY" "$APP_DIR/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/jarvis"
ok "commande « jarvis »"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) warn "ajoute $BIN_DIR à ton PATH pour taper « jarvis » partout" ;; esac

if [ "$OS" = "Darwin" ]; then
  # Une vraie application : nom « Jarvis » dans les demandes d'autorisation, pas d'icône dans le Dock
  mkdir -p "$MAC_APP/Contents/MacOS"
  cat > "$MAC_APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Jarvis</string>
  <key>CFBundleDisplayName</key><string>Jarvis</string>
  <key>CFBundleIdentifier</key><string>local.jarvis.assistant</string>
  <key>CFBundleExecutable</key><string>Jarvis</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Jarvis écoute ta voix pour répondre à tes demandes. Tout reste sur ton ordinateur.</string>
</dict></plist>
EOF
  cat > "$MAC_APP/Contents/MacOS/Jarvis" <<EOF
#!/bin/bash
cd "$APP_DIR"
exec "$PY" "$APP_DIR/main.py" --voice --background
EOF
  chmod +x "$MAC_APP/Contents/MacOS/Jarvis"
  ok "application $MAC_APP"

  AGENT="$HOME/Library/LaunchAgents/local.jarvis.assistant.plist"
  if [ "$AUTOSTART" = 1 ]; then
    mkdir -p "$(dirname "$AGENT")"
    cat > "$AGENT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.jarvis.assistant</string>
  <key>ProgramArguments</key><array><string>/usr/bin/open</string><string>-a</string><string>$MAC_APP</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
EOF
    ok "lancement automatique à l'ouverture de session"
  else
    rm -f "$AGENT"
  fi
else
  DESKTOP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/jarvis.desktop"
  mkdir -p "$(dirname "$DESKTOP")"
  cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Jarvis (voix)
Comment=Assistant personnel local : « Hey Jarvis » ou deux claquements de mains
Exec="$BIN_DIR/jarvis" --voice --background
Icon=audio-input-microphone
Terminal=false
Categories=Utility;
EOF
  # La fenêtre de discussion (texte) : sans --voice, main.py ouvre la fenêtre
  cat > "$(dirname "$DESKTOP")/jarvis-discussion.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Jarvis (discussion)
Comment=Discuter avec Jarvis par écrit
Exec="$BIN_DIR/jarvis" --background
Icon=internet-chat
Terminal=false
Categories=Utility;
EOF
  ok "entrées dans le menu des applications : Jarvis (voix) et Jarvis (discussion)"
  AUTO="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/jarvis.desktop"
  if [ "$AUTOSTART" = 1 ]; then
    mkdir -p "$(dirname "$AUTO")" && cp "$DESKTOP" "$AUTO"
    ok "lancement automatique à l'ouverture de session"
  else
    rm -f "$AUTO"
  fi
fi

# ------------------------------------------------------------ 8. autorisations
step "Autorisations"
if [ "$OS" = "Darwin" ]; then
  echo "  macOS protège certains dossiers (Documents, Bureau, Téléchargements, iCloud…)."
  echo "  Pour que Jarvis puisse y lire et chercher sans te le demander à chaque fois :"
  echo "    Réglages Système > Confidentialité et sécurité > Accès complet au disque > « + » > Jarvis"
  echo "  Le micro sera demandé automatiquement au premier lancement : accepte."
  if [ "$YES" = 0 ] && ask "Ouvrir maintenant le réglage « Accès complet au disque » ?"; then
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles" || true
    open -R "$MAC_APP" || true
  fi
else
  ok "aucune autorisation spéciale : Jarvis a accès à tout ce que ton compte peut ouvrir"
fi

bold ""
bold "✅ Jarvis est installé."
if [ "$OS" = "Darwin" ]; then
  echo "   Lance-le : ouvre « Jarvis » dans ~/Applications, ou tape « jarvis » dans un terminal."
else
  echo "   Lance-le : « Jarvis » dans le menu des applications, ou tape « jarvis » dans un terminal."
fi
echo "   Puis dis « Hey Jarvis » ou claque deux fois des mains."
echo "   Messages et erreurs : $DATA_DIR/jarvis.log — Désinstaller : $APP_DIR/installers/uninstall.sh"
