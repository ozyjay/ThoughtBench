#!/usr/bin/env bash
set -euo pipefail

CHECK_ONLY=0
PRE_DOWNLOAD=0
LAUNCH=0
MODEL_ID="google/gemma-4-E2B-it"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only)
      CHECK_ONLY=1
      shift
      ;;
    --pre-download-model)
      PRE_DOWNLOAD=1
      shift
      ;;
    --launch)
      LAUNCH=1
      shift
      ;;
    --model-id)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --model-id"
        exit 1
      fi
      MODEL_ID="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--check-only] [--pre-download-model] [--model-id <id>] [--launch]"
      exit 1
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script is for macOS only."
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="$HOME/.pyenv/versions/3.12.13/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing $PYTHON_BIN"
  echo "Install pyenv Python 3.12.13 first, for example:"
  echo "  PYTHON_CONFIGURE_OPTS=\"--enable-framework\" pyenv install 3.12.13"
  exit 1
fi

PY_VER="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
echo "Using pyenv Python: $PYTHON_BIN ($PY_VER)"

if ! "$PYTHON_BIN" -c "import tkinter" >/dev/null 2>&1; then
  cat <<'EOF'
pyenv Python is missing tkinter (_tkinter).
Rebuild Python with Homebrew tcl-tk available, for example:
  brew install tcl-tk openssl@3 readline sqlite3 xz zlib
  PYTHON_CONFIGURE_OPTS="--enable-framework" pyenv install -f 3.12.13
EOF
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "Creating .venv with --copies..."
  "$PYTHON_BIN" -m venv --copies .venv
fi

VENV_PY="$REPO_ROOT/.venv/bin/python"

if [[ $CHECK_ONLY -eq 1 ]]; then
  "$VENV_PY" --version
  "$VENV_PY" -c "import tkinter; print('tkinter=ok')"
  if "$VENV_PY" -c "import torch; print('torch=ok'); print('mps=' + str(torch.backends.mps.is_available()))"; then
    if ! "$VENV_PY" -c "import torch; raise SystemExit(0 if torch.backends.mps.is_available() else 1)"; then
      echo "warning=MPS unavailable; Thoughtbench will fall back to CPU and generation may be slow"
    fi
    :
  else
    echo "torch=missing (run setup without --check-only to install dependencies)"
  fi
  exit 0
fi

"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -r requirements-macos.txt

if ! "$VENV_PY" -c "import torch; raise SystemExit(0 if torch.backends.mps.is_available() else 1)"; then
  echo "Warning: PyTorch MPS is unavailable. Thoughtbench will fall back to CPU and generation may be slow."
fi

if [[ $PRE_DOWNLOAD -eq 1 ]]; then
  "$VENV_PY" -c "from huggingface_hub import snapshot_download; snapshot_download('$MODEL_ID'); print('Downloaded or found cached model: $MODEL_ID')"
fi

if [[ $LAUNCH -eq 1 ]]; then
  "$VENV_PY" app.py
else
  echo "Setup complete. Launch with:"
  echo "  bash ./scripts/Setup-Thoughtbench-macos.sh --launch"
fi
