#!/usr/bin/env bash
# Désinstallation de Jarvis (macOS et Linux).  --yes : sans questions (garde tes données).
set -euo pipefail

OS="$(uname -s)"
YES=0; [ "${1:-}" = "--yes" ] && YES=1
if [ "$OS" = "Darwin" ]; then
  APP_DIR="${JARVIS_APP_DIR:-$HOME/Library/Application Support/Jarvis/app}"
  MAC_APP="${JARVIS_MAC_APP:-$HOME/Applications/Jarvis.app}"
else
  APP_DIR="${JARVIS_APP_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/jarvis/app}"
fi
BIN_DIR="${JARVIS_BIN_DIR:-$HOME/.local/bin}"

ask() {
  [ "$YES" = 1 ] && return 1
  printf '%s [o/N] ' "$1"; read -r r </dev/tty || r=""
  case "$r" in o|O|oui|Oui|OUI|y|Y) return 0 ;; *) return 1 ;; esac
}

if [ -d "$APP_DIR" ] && { [ ! -f "$APP_DIR/main.py" ] || [ ! -d "$APP_DIR/jarvis" ]; }; then
  echo "$APP_DIR ne ressemble pas à une installation de Jarvis : rien n'est supprimé."; exit 1
fi
pkill -f "$APP_DIR/main.py" 2>/dev/null || true
rm -rf "$APP_DIR" "$BIN_DIR/jarvis"
if [ "$OS" = "Darwin" ]; then
  rm -rf "$MAC_APP"
  rm -f "$HOME/Library/LaunchAgents/local.jarvis.assistant.plist"
  rmdir "$(dirname "$APP_DIR")" 2>/dev/null || true
else
  rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/jarvis.desktop" \
        "${XDG_DATA_HOME:-$HOME/.local/share}/applications/jarvis-discussion.desktop" \
        "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/jarvis.desktop"
  rmdir "$(dirname "$APP_DIR")" 2>/dev/null || true
fi
echo "✓ Jarvis est désinstallé."

DATA_DIR="${JARVIS_HOME:-$HOME/.jarvis}"
if ask "Supprimer aussi ta configuration, ton historique et tes alarmes ($DATA_DIR) ?"; then
  rm -rf "$DATA_DIR" && echo "✓ données supprimées"
else
  echo "  Données conservées dans $DATA_DIR"
fi
echo "  Ollama et ses modèles ne sont pas touchés (ils peuvent servir à d'autres programmes)."
echo "  Pour libérer leur place : ollama rm qwen2.5:3b qwen2.5:7b"
