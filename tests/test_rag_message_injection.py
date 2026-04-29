import unittest
import shutil
import uuid
from pathlib import Path

from thoughtbench.behaviour import BehaviourMixin
from thoughtbench.knowledge import KnowledgeIndex, KnowledgeSettings, build_knowledge_index, knowledge_folder


class WorkspaceTemporaryDirectory:
    def __enter__(self):
        base = Path("tests") / "tmp_sandbox_check"
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / f"profile_{uuid.uuid4().hex}"
        self.path.mkdir(parents=True)
        return str(self.path)

    def __exit__(self, exc_type, exc, traceback):
        shutil.rmtree(self.path, ignore_errors=True)


class FakeText:
    def __init__(self, text):
        self.text = text

    def get(self, _start, _end):
        return self.text


class FakeApp(BehaviourMixin):
    def __init__(self):
        self.system_prompt = FakeText("You are helpful.")
        self.messages = [{"role": "user", "content": "Where is HF_HOME configured?"}]
        self.knowledge_index = KnowledgeIndex.from_chunks(
            [
                (
                    "setup.md#0001",
                    "setup.md",
                    "HF_HOME controls the Hugging Face cache location.",
                )
            ]
        )
        self.knowledge_settings = KnowledgeSettings()
        self.knowledge_index_stale = False
        self.log_dir = None
        self.last_retrieved_knowledge = []
        self.logged = []
        self.diagnostics = []
        self.statuses = []
        self.status_var = self

    def _save_system_prompt(self):
        self.saved_prompt = True

    def _append_log_entry(self, role, content):
        self.logged.append((role, content))

    def _capture_diagnostic(self, text, tag):
        self.diagnostics.append((text, tag))

    def set(self, value):
        self.statuses.append(value)


class RagMessageInjectionTests(unittest.TestCase):
    def test_build_messages_injects_retrieved_context_for_latest_user_message(self):
        app = FakeApp()

        messages = app._build_messages()

        self.assertEqual(messages[0], {"role": "system", "content": "You are helpful."})
        self.assertEqual(messages[-1], app.messages[-1])
        self.assertEqual(messages[-2]["role"], "system")
        self.assertIn("Retrieved knowledge files", messages[-2]["content"])
        self.assertIn("setup.md#0001", messages[-2]["content"])
        self.assertEqual(app.messages, [{"role": "user", "content": "Where is HF_HOME configured?"}])
        self.assertEqual(app.last_retrieved_knowledge[0].chunk.source, "setup.md")
        self.assertEqual(app.logged[0][0], "Knowledge")

    def test_build_messages_writes_retrieved_knowledge_details_to_diagnostics(self):
        app = FakeApp()

        app._build_messages()

        self.assertEqual(app.diagnostics[0][1], "diagnostic_meta")
        self.assertIn("Retrieved knowledge snippets", app.diagnostics[0][0])
        self.assertIn("[setup.md#0001]", app.diagnostics[0][0])
        self.assertIn("score=", app.diagnostics[0][0])
        self.assertIn("matched=hf_home", app.diagnostics[0][0])
        self.assertIn("HF_HOME controls the Hugging Face cache location.", app.diagnostics[0][0])

    def test_build_messages_skips_retrieval_when_profile_index_is_stale(self):
        with WorkspaceTemporaryDirectory() as tmp:
            profile = Path(tmp)
            source_dir = knowledge_folder(profile)
            source_dir.mkdir()
            note = source_dir / "setup.md"
            note.write_text("HF_HOME controls the Hugging Face cache location.", encoding="utf-8")
            index = build_knowledge_index(profile)
            note.write_text("Changed content makes index stale.", encoding="utf-8")

            app = FakeApp()
            app.log_dir = profile
            app.knowledge_index = index

            messages = app._build_messages()

            self.assertEqual(messages, [{"role": "system", "content": "You are helpful."}] + app.messages)
            self.assertEqual(app.last_retrieved_knowledge, [])
            self.assertTrue(app.knowledge_index_stale)
            self.assertIn("Knowledge index is stale - rebuild recommended.", app.statuses)
            self.assertIn(("Knowledge", "Knowledge index is stale - rebuild recommended."), app.logged)


if __name__ == "__main__":
    unittest.main()
