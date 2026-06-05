import types
import unittest

from thoughtbench.ui import ThoughtbenchApp


class ReadonlyShortcutTests(unittest.TestCase):
    def setUp(self):
        self.app = ThoughtbenchApp.__new__(ThoughtbenchApp)

    def test_readonly_display_allows_macos_command_copy(self):
        event = types.SimpleNamespace(state=0x10, keysym="c")

        self.assertIsNone(self.app._block_readonly_edit(event))


if __name__ == "__main__":
    unittest.main()
