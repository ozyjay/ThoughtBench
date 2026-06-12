import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


class MacOSBuildScriptTests(unittest.TestCase):
    def test_build_script_refuses_sudo_builds(self):
        script = Path("scripts/Build-macos.sh")

        content = script.read_text(encoding="utf-8")

        self.assertIn("Do not run this build script with sudo", content)
        self.assertIn("EUID", content)

    def test_repair_command_changes_owner_without_group(self):
        script = Path("scripts/Build-macos.sh")

        content = script.read_text(encoding="utf-8")

        self.assertIn('sudo chown -R \\"$USER\\"', content)
        self.assertNotIn('"$USER":"$(id -gn)"', content)

    def test_build_script_checks_effective_writability_not_owner_bits(self):
        script = Path("scripts/Build-macos.sh")

        content = script.read_text(encoding="utf-8")

        self.assertIn("[[ ! -w \"$candidate_dir\" ]]", content)
        self.assertNotIn("! -perm -u+w", content)

    def test_clean_reports_unwritable_dist_before_rm_rf(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            scripts_dir = repo / "scripts"
            scripts_dir.mkdir()
            build_script = scripts_dir / "Build-macos.sh"
            shutil.copy2("scripts/Build-macos.sh", build_script)

            venv_python = repo / ".venv" / "bin" / "python"
            venv_python.parent.mkdir(parents=True)
            venv_python.write_text("#!/usr/bin/env bash\nexit 99\n", encoding="utf-8")
            venv_python.chmod(0o755)

            blocked_output = repo / "dist" / "Thoughtbench"
            blocked_output.mkdir(parents=True)
            (blocked_output / "artifact.txt").write_text("owned elsewhere\n", encoding="utf-8")

            original_mode = stat.S_IMODE(blocked_output.stat().st_mode)
            blocked_output.chmod(0o555)
            self.addCleanup(lambda: blocked_output.exists() and blocked_output.chmod(original_mode))

            result = subprocess.run(
                ["bash", str(build_script), "--clean"],
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Build output is not writable", result.stderr + result.stdout)
        self.assertIn("sudo chown -R", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
