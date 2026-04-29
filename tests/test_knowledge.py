import shutil
import unittest
import uuid
from pathlib import Path

from thoughtbench.knowledge import (
    DEFAULT_KNOWLEDGE_SETTINGS,
    KNOWLEDGE_SETTINGS_FILE_NAME,
    KnowledgeIndex,
    KnowledgeSettings,
    build_knowledge_index,
    chunk_text,
    format_retrieved_context,
    index_is_stale,
    knowledge_folder,
    knowledge_index_folder,
    load_knowledge_settings,
    load_knowledge_index,
    save_knowledge_settings,
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

    def test_retrieve_ignores_stop_word_only_overlap(self):
        index = KnowledgeIndex.from_chunks(
            [("notes.md#0001", "notes.md", "Use concise markdown answers for general writing tasks.")]
        )

        self.assertEqual(index.retrieve("What is this for?", top_k=3), [])

    def test_retrieve_filters_below_minimum_score(self):
        index = KnowledgeIndex.from_chunks(
            [("setup.md#0001", "setup.md", "HF_HOME controls the Hugging Face cache location.")]
        )

        results = index.retrieve("HF_HOME", minimum_score=10.0)

        self.assertEqual(results, [])

    def test_retrieve_filters_below_minimum_matched_terms(self):
        index = KnowledgeIndex.from_chunks(
            [("setup.md#0001", "setup.md", "HF_HOME controls the Hugging Face cache location.")]
        )

        results = index.retrieve("HF_HOME configured", minimum_matched_terms=2)

        self.assertEqual(results, [])

    def test_retrieve_reports_matched_terms(self):
        index = KnowledgeIndex.from_chunks(
            [("setup.md#0001", "setup.md", "HF_HOME controls the Hugging Face cache location.")]
        )

        results = index.retrieve("Where is HF_HOME configured?")

        self.assertEqual(results[0].matched_terms, ("hf_home",))
        self.assertEqual(results[0].matched_term_count, 1)

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

    def test_load_knowledge_settings_uses_defaults_when_missing_or_invalid(self):
        with WorkspaceTemporaryDirectory() as tmp:
            profile = Path(tmp)

            self.assertEqual(load_knowledge_settings(profile), DEFAULT_KNOWLEDGE_SETTINGS)

            (profile / KNOWLEDGE_SETTINGS_FILE_NAME).write_text(
                '{"top_k": -1, "minimum_score": "bad"}',
                encoding="utf-8",
            )

            self.assertEqual(load_knowledge_settings(profile), DEFAULT_KNOWLEDGE_SETTINGS)

    def test_save_and_load_knowledge_settings_round_trip(self):
        with WorkspaceTemporaryDirectory() as tmp:
            profile = Path(tmp)
            settings = KnowledgeSettings(
                top_k=3,
                context_char_budget=1200,
                chunk_size=20,
                chunk_overlap=5,
                minimum_score=0.75,
                minimum_matched_terms=2,
            )

            save_knowledge_settings(profile, settings)

            self.assertEqual(load_knowledge_settings(profile), settings)

    def test_build_index_uses_chunk_settings(self):
        with WorkspaceTemporaryDirectory() as tmp:
            profile = Path(tmp)
            source_dir = knowledge_folder(profile)
            source_dir.mkdir()
            (source_dir / "notes.md").write_text(
                "one two three four five six seven eight nine ten",
                encoding="utf-8",
            )

            index = build_knowledge_index(
                profile,
                KnowledgeSettings(chunk_size=4, chunk_overlap=1),
            )

            self.assertGreater(len(index.chunks), 1)
            self.assertEqual(index.chunks[0].text, "one two three four")
            self.assertTrue(index.chunks[1].text.startswith("four five"))

    def test_index_is_stale_when_chunk_settings_change(self):
        with WorkspaceTemporaryDirectory() as tmp:
            profile = Path(tmp)
            source_dir = knowledge_folder(profile)
            source_dir.mkdir()
            (source_dir / "notes.md").write_text("one two three four five six", encoding="utf-8")

            built = build_knowledge_index(profile, KnowledgeSettings(chunk_size=4, chunk_overlap=1))

            self.assertFalse(index_is_stale(profile, built, KnowledgeSettings(chunk_size=4, chunk_overlap=1)))
            self.assertTrue(index_is_stale(profile, built, KnowledgeSettings(chunk_size=5, chunk_overlap=1)))

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
