# Thoughtbench

Run local thinking-capable **Gemma 4** and **Qwen3** models in a Tk desktop chat app.

This branch is focused on macOS, especially Apple Silicon with PyTorch MPS. It
omits the alternate platform setup path from the main branch.

## Quick macOS Setup

Install helper dependencies once:

```bash
brew install pyenv tcl-tk openssl@3 readline sqlite3 xz zlib
```

Install Python 3.12.13 in pyenv if needed:

```bash
PYTHON_CONFIGURE_OPTS="--enable-framework" pyenv install -s 3.12.13
```

Run setup:

```bash
bash ./scripts/Setup-Thoughtbench-macos.sh
```

Optional checks and model pre-download:

```bash
bash ./scripts/Setup-Thoughtbench-macos.sh --check-only
bash ./scripts/Setup-Thoughtbench-macos.sh --pre-download-model
bash ./scripts/Setup-Thoughtbench-macos.sh --pre-download-model --model-id Qwen/Qwen3-0.6B
```

Launch:

```bash
bash ./scripts/Setup-Thoughtbench-macos.sh --launch
```

## Manual Developer Setup

```bash
PYTHON_CONFIGURE_OPTS="--enable-framework" pyenv install -s 3.12.13
$HOME/.pyenv/versions/3.12.13/bin/python -m venv --copies .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-macos.txt
./.venv/bin/python app.py
```

Optional Hugging Face login:

```bash
./.venv/bin/hf auth login
```

Model files are downloaded into the Hugging Face cache. Set `HF_HOME` before
setup or launch if you want the cache somewhere specific.

## Behaviour Profiles

On first launch, Thoughtbench creates a default Behaviour Profile under:

```text
~/.thoughtbench/profiles/Default
```

The `~/.thoughtbench` folder is the profile container. Each profile folder stores
its own Assistant Behaviour, prompt history, restored conversation, transcripts,
and diagnostics:

```text
~/.thoughtbench/profiles/Default/system_prompt.md
~/.thoughtbench/profiles/Default/system_prompt_history.json
~/.thoughtbench/profiles/Default/conversation.json
~/.thoughtbench/profiles/Default/gemma4_chat_YYYYMMDD_HHMMSS.md
~/.thoughtbench/profiles/Default/diagnostics_YYYYMMDD_HHMMSS.log
```

Use `Show Behaviour` in the app to switch profiles, create a new profile, add an
existing profile folder, or restore earlier Assistant Behaviour versions.

Older root-level `~/.thoughtbench` profile files are moved into
`~/.thoughtbench/profiles/Default` automatically.

## Models

The app asks which curated model to load at startup and remembers the selection.
Current curated options include:

| Family | Model ID |
| --- | --- |
| Gemma | `google/gemma-4-E2B-it` |
| Gemma | `google/gemma-4-E4B-it` |
| Gemma | `google/gemma-4-26B-A4B-it` |
| Gemma | `google/gemma-4-31B-it` |
| Qwen | `Qwen/Qwen3-0.6B` |
| Qwen | `Qwen/Qwen3-1.7B` |
| Qwen | `Qwen/Qwen3-4B` |
| Qwen | `Qwen/Qwen3-8B` |

Gemma thinking output uses channel markers. Qwen3 thinking output uses
`<think>...</think>` blocks.

## Command-Line Helpers

Interactive chat:

```bash
./.venv/bin/python chat.py --model-id Qwen/Qwen3-0.6B --think
```

Single-shot generation:

```bash
./.venv/bin/python generate.py "Explain quicksort in Python"
./.venv/bin/python generate.py --think "What is 25 * 37?"
./.venv/bin/python generate.py --max-tokens 512 --system "You are a poet." "Write a haiku about local models"
```

## Model Loading

On Apple Silicon, the app tries to load models on MPS. You can override the load
mode if needed:

```bash
THOUGHTBENCH_LOAD_MODE=auto ./.venv/bin/python app.py
THOUGHTBENCH_LOAD_MODE=bf16 ./.venv/bin/python app.py
```

## Build The macOS App

```bash
bash ./scripts/Build-macos.sh --clean
```

The build script installs `requirements-build-macos.txt`, generates
`assets/app-icon.icns` from `assets/app-icon.png`, and runs PyInstaller.

The app bundle is written to:

```text
dist/Thoughtbench.app
```

Install it to `/Applications` with:

```bash
bash ./scripts/Install-macos.sh
```

## Diagnostics

Use `Actions` > `Show Diagnostics` to show or hide captured stdout/stderr output.
Diagnostics are captured even while the pane is hidden and are saved beside the
current profile's chat logs.
