#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script is for macOS only."
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_APP="$REPO_ROOT/dist/Thoughtbench.app"
DEST_APP="/Applications/Thoughtbench.app"

if [[ ! -d "$SOURCE_APP" ]]; then
  echo "Missing app bundle: dist/Thoughtbench.app"
  echo "Build it first:"
  echo "  bash ./scripts/Build-macos.sh --clean"
  exit 1
fi

install_without_admin() {
  rm -rf "$DEST_APP"
  ditto "$SOURCE_APP" "$DEST_APP"
  touch "$DEST_APP"
}

install_with_admin() {
  /usr/bin/osascript - "$SOURCE_APP" "$DEST_APP" <<'APPLESCRIPT'
on run argv
  set sourceApp to item 1 of argv
  set destApp to item 2 of argv
  set commandText to "rm -rf " & quoted form of destApp & " && ditto " & quoted form of sourceApp & " " & quoted form of destApp & " && touch " & quoted form of destApp
  do shell script commandText with administrator privileges
end run
APPLESCRIPT
}

refresh_launch_services() {
  local lsregister="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
  if [[ -x "$lsregister" ]]; then
    "$lsregister" -f "$DEST_APP" >/dev/null 2>&1 || true
  fi
}

echo "Installing dist/Thoughtbench.app to /Applications/Thoughtbench.app..."

if install_without_admin 2>/dev/null; then
  :
else
  echo "Administrator permission is required to install to /Applications."
  install_with_admin
fi

refresh_launch_services

echo "Installed: $DEST_APP"
echo "Launch it from Finder, Spotlight, or with:"
echo "  open /Applications/Thoughtbench.app"
