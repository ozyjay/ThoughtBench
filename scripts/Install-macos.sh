#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script is for macOS only."
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_APP="$REPO_ROOT/dist/Thoughtbench.app"
DEST_DIR="$HOME/Applications"
DEST_APP="$DEST_DIR/Thoughtbench.app"

if [[ ! -d "$SOURCE_APP" ]]; then
  echo "Missing app bundle: dist/Thoughtbench.app"
  echo "Build it first:"
  echo "  bash ./scripts/Build-macos.sh --clean"
  exit 1
fi

install_app() {
  mkdir -p "$DEST_DIR"
  rm -rf "$DEST_APP"
  ditto "$SOURCE_APP" "$DEST_APP"
  touch "$DEST_APP"
}

refresh_launch_services() {
  local lsregister="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  if [[ -x "$lsregister" ]]; then
    "$lsregister" -f "$DEST_APP" >/dev/null 2>&1 || true
  fi
}

echo "Installing dist/Thoughtbench.app to $DEST_APP..."

install_app

refresh_launch_services

echo "Installed: $DEST_APP"
echo "Launch it from Finder, Spotlight, or with:"
echo "  open \"$DEST_APP\""
