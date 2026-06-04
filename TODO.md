# TODO

## C# / ONNX CUDA Migration

- Validate a small ONNX Runtime GenAI smoke model on Windows/NVIDIA hardware.
- Decide which Gemma/Qwen models should be converted or replaced in the C# catalog.
- Expand the WPF shell toward full UI parity with the Python/Tk app.
- Add installer shortcut support for `dist\csharp\app` after publish output is stable.
- Remove Python code only after C# desktop, CLI, setup/build scripts, docs, and tests pass acceptance checks.

## Future: Hybrid Knowledge Retrieval

Profile knowledge files and BM25 retrieval are implemented. The current system:

- Indexes profile-local `.md` and `.txt` files.
- Builds a local BM25 keyword index.
- Retrieves snippets for each desktop chat message.
- Applies minimum score and matched-term thresholds.
- Shows source, score, matched terms, and snippet previews.
- Warns and skips retrieval when the index is stale.
- Stores retrieval settings per Behaviour Profile.

BM25 should remain the exact-match anchor because it is strong for command names,
file paths, settings, UI labels, policy terms, and error strings.

Future vector search should cover semantic or vague questions where the user
asks in different words from the knowledge files. Long term, prefer hybrid
retrieval: BM25 plus vector search, then merge or rerank results before sending
context to the model.
