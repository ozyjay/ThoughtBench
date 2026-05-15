# Agent Notes

This branch is macOS-focused and is not intended to be PR'd back to the main
branch as-is. Keep changes aligned with the local branch direction rather than
preserving cross-platform compatibility.

## Branch Direction

- Treat macOS as the only supported setup, runtime, and build target.
- Do not reintroduce Windows setup scripts, Windows requirements files, CUDA
  load modes, `bitsandbytes`, NVIDIA/NVML stats, or `.ico` packaging.
- Keep the current Tk app runnable while the UI is being refactored.
- Prefer PySide6 / Qt for Python for the next UI layer.
- Extract model execution behind UI-neutral request/event APIs before moving
  significant behaviour into a new UI.

## Runtime Architecture

The intended model boundary is:

```text
GenerationRequest -> ModelRunner.stream(request) -> GenerationEvent
```

Model loading, generation, thinking parsing, cancellation, and diagnostics
should not depend on Tkinter, PySide6, or any other UI toolkit. UI code should
subscribe to events and render them.

The current Tk app has a main-thread UI event queue. Background threads should
post UI work through that path instead of calling Tk methods directly.

## Profiles And Storage

`~/.thoughtbench` is a profile container, not a single profile.

Expected profile layout:

```text
~/.thoughtbench/profiles/Default/
  system_prompt.md
  system_prompt_history.json
  conversation.json
  gemma4_chat_YYYYMMDD_HHMMSS.md
  diagnostics_YYYYMMDD_HHMMSS.log
```

Keep profile-specific data inside the selected profile folder.

## App Icon

The macOS build path is:

```text
assets/app-icon.png -> assets/app-icon.icns
```

Do not add back `assets/app-icon.ico`.

## Verification

Before claiming a coding change is complete, run the relevant subset of:

```bash
./.venv/bin/python -m unittest discover
./.venv/bin/python -m compileall -f app.py chat.py generate.py thoughtbench tests
bash -n scripts/Setup-Thoughtbench-macos.sh scripts/Build-macos.sh
git diff --check
```

For setup changes, also run:

```bash
./scripts/Setup-Thoughtbench-macos.sh --check-only
```

## Documentation Split

- `README.md`: user setup, launch, build, profiles, and diagnostics.
- `TODO.md`: lightweight branch roadmap and unfinished ideas.
- `AGENTS.md`: instructions for future coding agents working in this repo.
