# TODO

## Future: Profile Knowledge Files and RAG

Add support for knowledge files so users do not have to paste large reference
packs into Assistant Behaviour. Assistant Behaviour should remain the place for
stable instructions, role, tone, formatting preferences, and always-on rules.
Knowledge files should hold larger factual/project reference material that is
retrieved only when relevant.

Proposed profile layout:

```text
.test.gemma4\
  system_prompt.md
  conversation.json
  knowledge\
    project-notes.md
    policies.md
    examples.md
  knowledge_index\
    chunks.json
    vectors.faiss
```

Suggested first version:

- Add a profile-specific `knowledge\` folder.
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

