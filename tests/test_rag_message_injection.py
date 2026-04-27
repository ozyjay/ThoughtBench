import unittest

from thoughtbench.behaviour import BehaviourMixin
from thoughtbench.knowledge import KnowledgeIndex


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
        self.last_retrieved_knowledge = []
        self.logged = []

    def _save_system_prompt(self):
        self.saved_prompt = True

    def _append_log_entry(self, role, content):
        self.logged.append((role, content))


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


if __name__ == "__main__":
    unittest.main()
