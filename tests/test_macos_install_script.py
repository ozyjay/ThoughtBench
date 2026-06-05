import os
import unittest
from pathlib import Path


class MacOSInstallScriptTests(unittest.TestCase):
    def test_install_script_targets_dist_bundle_and_applications(self):
        script = Path("scripts/Install-macos.sh")

        self.assertTrue(script.exists())
        self.assertTrue(os.access(script, os.X_OK))

        content = script.read_text(encoding="utf-8")
        self.assertIn("dist/Thoughtbench.app", content)
        self.assertIn("/Applications/Thoughtbench.app", content)
        self.assertIn("with administrator privileges", content)


if __name__ == "__main__":
    unittest.main()
