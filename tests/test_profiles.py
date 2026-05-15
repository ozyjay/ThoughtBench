import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from thoughtbench.config import APP_FOLDER_NAME, SYSTEM_PROMPT_FILE_NAME
from thoughtbench.persistence import PersistenceMixin


class _Status:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _ProfileResolver(PersistenceMixin):
    def __init__(self):
        self.root = None
        self.log_dir = None
        self.status_var = _Status()
        self.profile_combo = None
        self._settings = {}

    def _read_settings(self):
        return dict(self._settings)

    def _write_settings(self, settings):
        self._settings = dict(settings)

    def _get_system_prompt(self):
        return "You are a helpful assistant."


class ProfileSetupTests(unittest.TestCase):
    def test_first_run_creates_default_profile_inside_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            resolver = _ProfileResolver()
            with patch("pathlib.Path.home", return_value=home):
                profile_dir = resolver._resolve_log_dir()

            self.assertEqual(
                profile_dir,
                home / APP_FOLDER_NAME / "profiles" / "Default",
            )
            self.assertTrue(profile_dir.is_dir())
            self.assertTrue((profile_dir / SYSTEM_PROMPT_FILE_NAME).exists())
            self.assertFalse((home / APP_FOLDER_NAME / SYSTEM_PROMPT_FILE_NAME).exists())

    def test_existing_root_profile_setting_migrates_to_default_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root_profile = home / APP_FOLDER_NAME
            root_profile.mkdir()
            (root_profile / SYSTEM_PROMPT_FILE_NAME).write_text("Legacy prompt", encoding="utf-8")
            resolver = _ProfileResolver()
            resolver._settings = {"active_profile_dir": str(root_profile)}

            with patch("pathlib.Path.home", return_value=home):
                profile_dir = resolver._resolve_log_dir()

            expected_profile = home / APP_FOLDER_NAME / "profiles" / "Default"
            self.assertEqual(profile_dir, expected_profile)
            self.assertEqual(
                (expected_profile / SYSTEM_PROMPT_FILE_NAME).read_text(encoding="utf-8"),
                "Legacy prompt",
            )
            self.assertFalse((root_profile / SYSTEM_PROMPT_FILE_NAME).exists())

    def test_empty_root_profile_setting_uses_default_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            root_profile = home / APP_FOLDER_NAME
            root_profile.mkdir()
            resolver = _ProfileResolver()
            resolver._settings = {"active_profile_dir": str(root_profile)}

            with patch("pathlib.Path.home", return_value=home):
                profile_dir = resolver._resolve_log_dir()

            expected_profile = home / APP_FOLDER_NAME / "profiles" / "Default"
            self.assertEqual(profile_dir, expected_profile)
            self.assertTrue((expected_profile / SYSTEM_PROMPT_FILE_NAME).exists())


if __name__ == "__main__":
    unittest.main()
