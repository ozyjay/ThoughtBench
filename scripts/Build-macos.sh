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

"$VENV_PY" -m PyInstaller --noconfirm Thoughtbench.spec

echo
echo "Build complete: dist/Thoughtbench/Thoughtbench"
