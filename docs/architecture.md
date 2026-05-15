# Thoughtbench Architecture

This branch is a macOS-focused local model workbench. It currently uses Tkinter
for the desktop UI, but the intended direction is to move toward PySide6 / Qt for
Python after the model runtime is separated from UI concerns.

## Current Shape

```text
app.py
  creates Tk root
  instantiates ThoughtbenchApp

thoughtbench/ui.py
  builds the Tk interface
  owns high-level UI state
  starts profile setup, diagnostics, stats, and model loading

thoughtbench/runtime.py
  loads models
  streams generation
  manages token stats, progress state, cancellation, and app shutdown

thoughtbench/model_loading.py
  chooses load mode and device placement
  creates processor/tokenizer and model objects

thoughtbench/model.py
  parses generated text into thinking and response content

thoughtbench/persistence.py
  manages profiles, conversation state, system prompts, and transcript logs

thoughtbench/behaviour.py
  rewrites Assistant Behaviour using the loaded local model
```

The Tk UI is kept working for now. Background work posts UI callbacks through a
main-thread event queue so worker threads do not call Tk methods directly.

## Profile Storage

`~/.thoughtbench` is a container for profile folders.

```text
~/.thoughtbench/profiles/Default/
  system_prompt.md
  system_prompt_history.json
  conversation.json
  gemma4_chat_YYYYMMDD_HHMMSS.md
  diagnostics_YYYYMMDD_HHMMSS.log
```

Profile-specific data should remain inside the selected profile folder. The app
migrates older root-level `~/.thoughtbench` profile files into
`~/.thoughtbench/profiles/Default`.

## Model Loading

The macOS branch supports these load modes:

- `auto`
- `bf16`

Unsupported or legacy values fall back to `auto`.

On Apple Silicon, the app tries to use PyTorch MPS. If MPS is unavailable, it
falls back to CPU with `float32`. CPU fallback is useful for correctness testing
but can be very slow for real chat.

## Target Runtime Boundary

The next major refactor should isolate model execution behind a UI-neutral API:

```text
GenerationRequest -> ModelRunner.stream(request) -> GenerationEvent
```

The goal is for loading, generation, thinking parsing, cancellation, and errors
to be expressible without importing Tkinter or PySide6.

Possible request fields:

- model id
- messages
- system prompt
- thinking mode
- max tokens
- temperature
- top-p
- top-k
- stop/cancel token or event

Possible event types:

- `load_started`
- `load_progress`
- `load_finished`
- `generation_started`
- `token`
- `thinking_token`
- `generation_finished`
- `cancelled`
- `error`

## UI Migration Direction

PySide6 / Qt for Python is the preferred next UI toolkit for this branch.

Reasons:

- stronger macOS desktop behaviour than Tkinter
- clearer worker/signal model for background generation
- better rich text widgets for chat transcripts and markdown-like output
- mature packaging path with PyInstaller
- keeps the Python model runtime in-process while allowing a more capable UI

Suggested migration phases:

1. Extract `GenerationRequest`, `GenerationEvent`, and `ModelRunner`.
2. Add tests for generation events, cancellation, and thinking parsing.
3. Build a small PySide6 shell that can load a model and stream one response.
4. Port profile selection, conversation persistence, and system prompt editing.
5. Port thinking display, behaviour rewrite, diagnostics, token stats, and build
   scripts.
6. Remove the Tk UI after feature parity.

## macOS Build

The app icon path is:

```text
assets/app-icon.png -> assets/app-icon.icns
```

The build script should remain bash-only and should not restore Windows or CUDA
packaging paths.

## Verification

Common verification commands:

```bash
./.venv/bin/python -m unittest discover
./.venv/bin/python -m compileall -f app.py chat.py generate.py thoughtbench tests
bash -n scripts/Setup-Thoughtbench-macos.sh scripts/Build-macos.sh
git diff --check
```

For setup or environment changes:

```bash
./scripts/Setup-Thoughtbench-macos.sh --check-only
```
