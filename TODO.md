# Thoughtbench TODO

This branch is macOS-focused and is not intended to be PR'd back to the main
branch as-is. Use this file as a lightweight local roadmap for branch-specific
architecture work.

## Current: Move the UI Away From Tkinter

Tkinter is now stable enough to keep testing the app, but it is a weak long-term
fit for this branch. The app needs rich streaming chat output, background model
loading, careful shutdown, profile management, markdown rendering, and macOS app
packaging. Those concerns are easier to handle with a UI toolkit that has a
stronger main-thread/event model.

Recommended target: PySide6 / Qt for Python.

Migration goals:

- Keep model loading and generation logic independent from any UI toolkit.
- Move background work to Qt workers/signals instead of Tk callbacks.
- Replace Tk text widgets with Qt chat/transcript widgets that can handle
  streamed rich text more naturally.
- Keep profile storage in `~/.thoughtbench/profiles/<Profile Name>/`.
- Keep the macOS app icon path as `assets/app-icon.png -> assets/app-icon.icns`.
- Keep the current Tk app runnable until the Qt app reaches feature parity.

Suggested phases:

1. Extract generation into UI-neutral request/event objects.
2. Add a small PySide6 app shell that can select a model, load it, and stream one
   response.
3. Port profile selection, conversation persistence, and system prompt editing.
4. Port thinking-mode display, behaviour rewrite, diagnostics, and token stats.
5. Update packaging scripts to build the Qt app.
6. Remove the Tk UI once the Qt app covers the same workflows.

## Next: ModelRunner Refactor

Target shape:

```text
GenerationRequest -> ModelRunner.stream(request) -> GenerationEvent
```

The refactor should happen before or alongside the PySide6 prototype so the new
UI does not inherit Tk-specific runtime coupling.

Initial event types to consider:

- `load_started`
- `load_progress`
- `load_finished`
- `generation_started`
- `token`
- `thinking_token`
- `generation_finished`
- `error`
- `cancelled`

## Future: Profile Knowledge Files and RAG

Add support for knowledge files so users do not have to paste large reference
packs into Assistant Behaviour. Assistant Behaviour should remain the place for
stable instructions, role, tone, formatting preferences, and always-on rules.
Knowledge files should hold larger factual/project reference material that is
retrieved only when relevant.

Proposed profile layout:

```text
~/.thoughtbench/profiles/Default/
  system_prompt.md
  conversation.json
  knowledge/
    project-notes.md
    policies.md
    examples.md
  knowledge_index/
    chunks.json
    vectors.faiss
```

Suggested first version:

- Add a profile-specific `knowledge/` folder.
- Support `.txt` and `.md` files first.
- Add a manual `Rebuild Knowledge Index` action.
- Chunk files into small passages and store chunk metadata locally.
- Retrieve the top 3-8 relevant chunks for each user message.
- Inject retrieved chunks into the prompt as temporary context.
- Show or log which knowledge chunks were injected.

Retrieval strategy:

- Start with BM25 / keyword retrieval because it is simple, fast, local, and
  strong for exact names, commands, file paths, UI labels, settings, and error
  strings.
- Add vector search later for semantic queries where the user asks in different
  words from the knowledge files.
- Long term, prefer hybrid retrieval: BM25 plus vector search, then merge or
  rerank results before sending context to Gemma.

Notes from discussion:

- Gemma 4 can reason well over retrieved chunks, so retrieval mostly needs to
  get the right evidence into context.
- Vector search also works when users use the same words as the knowledge pack,
  but it does not treat exact string overlap as sacred.
- BM25 often wins for exact project knowledge such as script names, command
  flags, file paths, config keys, UI labels, and error messages.
- Vector search is useful for conceptual or vague questions, such as asking
  about "the thing that stores old behaviour versions."
- Hybrid search is likely the best eventual user experience.

## Later: PyInstaller Bundle Hygiene

The macOS build currently works, but PyInstaller pulls in a broad set of hidden
imports from packages such as `accelerate`, including test utilities and optional
submodules that are not part of Thoughtbench's runtime path. During the app
build, PyInstaller also probes optional Torch/CUDA-related libraries even though
this branch is macOS-only.

Later cleanup:

- Audit `Thoughtbench.spec` hidden imports.
- Avoid collecting `accelerate.test_utils` and other non-runtime modules.
- Confirm bundle size before and after exclusions.
- Keep exclusions aligned with the macOS-only branch direction.
- Re-run an actual packaged app smoke test after trimming imports.
