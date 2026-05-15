#!/usr/bin/env bash
set -euo pipefail

CLEAN=0
SKIP_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean)
      CLEAN=1
      shift
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--clean] [--skip-install]"
      exit 1
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV_PY="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "Missing .venv Python. Run mac setup first:"
  echo "  bash ./scripts/Setup-Thoughtbench-macos.sh"
  exit 1
fi

if [[ $CLEAN -eq 1 ]]; then
  rm -rf build dist
fi

if [[ $SKIP_INSTALL -eq 0 ]]; then
  "$VENV_PY" -m pip install -r requirements-build-macos.txt
fi

# Generate .icns from app-icon.png for the macOS .app bundle when needed.
ICONSET="$REPO_ROOT/assets/AppIcon.iconset"
ICNS="$REPO_ROOT/assets/app-icon.icns"
if [[ ! -f "$ICNS" || "$REPO_ROOT/assets/app-icon.png" -nt "$ICNS" ]]; then
  rm -rf "$ICONSET"
  mkdir -p "$ICONSET"
  for SIZE in 16 32 128 256 512; do
    sips -z $SIZE $SIZE "$REPO_ROOT/assets/app-icon.png" --out "$ICONSET/icon_${SIZE}x${SIZE}.png" > /dev/null
  done
  # @2x variants
  sips -z 32   32   "$REPO_ROOT/assets/app-icon.png" --out "$ICONSET/icon_16x16@2x.png"  > /dev/null
  sips -z 64   64   "$REPO_ROOT/assets/app-icon.png" --out "$ICONSET/icon_32x32@2x.png"  > /dev/null
  sips -z 256  256  "$REPO_ROOT/assets/app-icon.png" --out "$ICONSET/icon_128x128@2x.png" > /dev/null
  sips -z 512  512  "$REPO_ROOT/assets/app-icon.png" --out "$ICONSET/icon_256x256@2x.png" > /dev/null
  sips -z 1024 1024 "$REPO_ROOT/assets/app-icon.png" --out "$ICONSET/icon_512x512@2x.png" > /dev/null
  ICON_GENERATED=1
  if ! iconutil -c icns "$ICONSET" -o "$ICNS"; then
    ICON_GENERATED=0
    rm -rf "$ICONSET"
    if [[ -f "$ICNS" ]]; then
      echo "Warning: iconutil could not regenerate $ICNS; using existing icon."
    else
      echo "Error: iconutil could not generate $ICNS and no existing icon is available."
      exit 1
    fi
  fi
  rm -rf "$ICONSET"
  if [[ $ICON_GENERATED -eq 1 ]]; then
    echo "Generated $ICNS"
  fi
else
  echo "Using existing $ICNS"
fi

# Always remove previous bundle outputs so deleted assets do not linger in
# incremental PyInstaller builds.
rm -rf dist/Thoughtbench.app dist/Thoughtbench

"$VENV_PY" -m PyInstaller --noconfirm Thoughtbench.spec
touch dist/Thoughtbench.app

echo
echo "Build complete: dist/Thoughtbench.app"
echo "Drag dist/Thoughtbench.app to /Applications to install."
