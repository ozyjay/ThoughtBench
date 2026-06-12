import os
import unittest
from pathlib import Path


class MacOSInstallScriptTests(unittest.TestCase):
    def test_install_script_targets_user_applications_without_admin_prompt(self):
        script = Path("scripts/Install-macos.sh")

        self.assertTrue(script.exists())
        self.assertTrue(os.access(script, os.X_OK))

        content = script.read_text(encoding="utf-8")
        self.assertIn("dist/Thoughtbench.app", content)
        self.assertIn('DEST_DIR="$HOME/Applications"', content)
        self.assertIn('DEST_APP="$DEST_DIR/Thoughtbench.app"', content)
        self.assertIn('mkdir -p "$DEST_DIR"', content)
        self.assertNotIn("/Applications/Thoughtbench.app", content)
        self.assertNotIn("with administrator privileges", content)
        self.assertNotIn("osascript", content)


if __name__ == "__main__":
    unittest.main()
