import shutil
import unittest
import uuid
from pathlib import Path

from thoughtbench.knowledge import (
    KnowledgeIndex,
    build_knowledge_index,
    chunk_text,
    format_retrieved_context,
    index_is_stale,
    knowledge_folder,
    knowledge_index_folder,
    load_knowledge_index,
)


class WorkspaceTemporaryDirectory:
    def __enter__(self):
        base = Path("tests") / "tmp_sandbox_check"
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / f"profile_{uuid.uuid4().hex}"
        self.path.mkdir(parents=True)
        return str(self.path)

    def __exit__(self, exc_type, exc, traceback):
        shutil.rmtree(self.path, ignore_errors=True)


class KnowledgeIndexTests(unittest.TestCase):
    def test_chunk_text_ignores_empty_text_and_keeps_metadata(self):
        self.assertEqual(chunk_text("   ", "empty.md"), [])

        chunks = chunk_text("Alpha beta gamma.\n\nDelta epsilon.", "notes.md", max_words=3, overlap_words=0)

        self.assertEqual([chunk.source for chunk in chunks], ["notes.md", "notes.md"])
        self.assertEqual([chunk.chunk_id for chunk in chunks], ["notes.md#0001", "notes.md#0002"])
        self.assertEqual(chunks[0].text, "Alpha beta gamma.")
        self.assertEqual(chunks[1].text, "Delta epsilon.")

    def test_build_index_reads_only_markdown_and_text_files(self):
        with WorkspaceTemporaryDirectory() as tmp:
            profile = Path(tmp)
            source_dir = knowledge_folder(profile)
            source_dir.mkdir()
            (source_dir / "project.md").write_text("Setup-Thoughtbench.ps1 uses HF_HOME.", encoding="utf-8")
            (source_dir / "policy.txt").write_text("Answer with file citations.", encoding="utf-8")
            (source_dir / "ignored.pdf").write_text("not indexed", encoding="utf-8")

            index = build_knowledge_index(profile)

            self.assertEqual({chunk.source for chunk in index.chunks}, {"project.md", "policy.txt"})
            self.assertTrue((knowledge_index_folder(profile) / "index.json").exists())

    def test_retrieve_ranks_exact_project_terms_highly(self):
        chunks = [
            ("setup.md#0001", "setup.md", "Setup-Thoughtbench.ps1 downloads models and respects HF_HOME."),
            ("style.md#0001", "style.md", "Use concise markdown answers for general writing tasks."),
        ]
        index = KnowledgeIndex.from_chunks(chunks)

        results = index.retrieve("How do I set HF_HOME for Setup-Thoughtbench.ps1?", top_k=2)

        self.assertEqual(results[0].chunk.source, "setup.md")
        self.assertGreater(results[0].score, 0)

    def test_retrieve_returns_empty_for_no_match(self):
        index = KnowledgeIndex.from_chunks(
            [("notes.md#0001", "notes.md", "Alpha beta gamma")]
        )

        self.assertEqual(index.retrieve("zzzz qqqq", top_k=3), [])

    def test_index_persistence_and_stale_detection(self):
        with WorkspaceTemporaryDirectory() as tmp:
            profile = Path(tmp)
            source_dir = knowledge_folder(profile)
            source_dir.mkdir()
            note = source_dir / "notes.md"
            note.write_text("first version", encoding="utf-8")

            built = build_knowledge_index(profile)
            loaded = load_knowledge_index(profile)

            self.assertEqual([chunk.text for chunk in loaded.chunks], [chunk.text for chunk in built.chunks])
            self.assertFalse(index_is_stale(profile, loaded))

            note.write_text("second version with extra text", encoding="utf-8")
            self.assertTrue(index_is_stale(profile, loaded))

    def test_corrupt_index_loads_as_empty(self):
        with WorkspaceTemporaryDirectory() as tmp:
            profile = Path(tmp)
            index_dir = knowledge_index_folder(profile)
            index_dir.mkdir()
            (index_dir / "index.json").write_text("{not json", encoding="utf-8")

            loaded = load_knowledge_index(profile)

            self.assertEqual(loaded.chunks, [])

    def test_format_retrieved_context_respects_budget_and_sources(self):
        index = KnowledgeIndex.from_chunks(
            [
                ("a.md#0001", "a.md", "alpha " * 100),
                ("b.md#0001", "b.md", "beta policy"),
            ]
        )
        results = index.retrieve("alpha beta policy", top_k=2)

        context = format_retrieved_context(results, max_chars=180)

        self.assertIn("Retrieved knowledge files", context)
        self.assertIn("[a.md#0001]", context)
        self.assertLessEqual(len(context), 220)


if __name__ == "__main__":
    unittest.main()
