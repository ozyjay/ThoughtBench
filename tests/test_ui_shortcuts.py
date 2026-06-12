import types
import unittest
import tkinter as tk

from thoughtbench.ui import ThoughtbenchApp


class _FakeRoot:
    def __init__(self):
        self.clipboard = None

    def clipboard_clear(self):
        self.clipboard = ""

    def clipboard_append(self, text):
        self.clipboard = text


class _FakeReadonlyText:
    def __init__(self, selected_text="selected text"):
        self.selected_text = selected_text
        self.bindings = {}
        self.configured = {}

    def configure(self, **kwargs):
        self.configured.update(kwargs)

    def bind(self, sequence, callback, add=None):
        self.bindings[sequence] = callback

    def get(self, start, end):
        if start == tk.SEL_FIRST and end == tk.SEL_LAST:
            return self.selected_text
        raise AssertionError((start, end))


class ReadonlyShortcutTests(unittest.TestCase):
    def setUp(self):
        self.app = ThoughtbenchApp.__new__(ThoughtbenchApp)

    def test_readonly_display_allows_macos_command_copy(self):
        event = types.SimpleNamespace(state=0x10, keysym="c")

        self.assertIsNone(self.app._block_readonly_edit(event))

    def test_readonly_command_copy_copies_selected_text(self):
        self.app.root = _FakeRoot()
        widget = _FakeReadonlyText("chosen words")

        result = self.app._copy_selected_readonly_text(widget)

        self.assertEqual(result, "break")
        self.assertEqual(self.app.root.clipboard, "chosen words")

    def test_readonly_display_binds_command_copy_to_selection_copy(self):
        self.app.root = _FakeRoot()
        widget = _FakeReadonlyText("chosen words")

        self.app._make_readonly_display(widget)
        result = widget.bindings["<Command-c>"](types.SimpleNamespace())

        self.assertEqual(result, "break")
        self.assertEqual(self.app.root.clipboard, "chosen words")


if __name__ == "__main__":
    unittest.main()
