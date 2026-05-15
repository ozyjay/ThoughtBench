"""Persistence helpers for settings, prompts, and conversations."""

import json
from pathlib import Path

from .config import (
    CONVERSATION_FILE_NAME,
    APP_FOLDER_NAME,
    LEGACY_APP_FOLDER_NAME,
    SETTINGS_DIR,
    SETTINGS_FILE,
    SYSTEM_PROMPT_FILE_NAME,
    SYSTEM_PROMPT_HISTORY_FILE_NAME,
)

DEFAULT_PROFILE_NAME = "Default"


def read_settings() -> dict:
    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return settings if isinstance(settings, dict) else {}


def write_settings(settings: dict):
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass


def default_profiles_root() -> Path:
    return Path.home() / APP_FOLDER_NAME / "profiles"


def default_profile_dir() -> Path:
    return default_profiles_root() / DEFAULT_PROFILE_NAME


def legacy_profile_roots() -> tuple[Path, ...]:
    return (
        Path.home() / LEGACY_APP_FOLDER_NAME,
        Path.cwd() / LEGACY_APP_FOLDER_NAME,
    )


def profile_label(profile_dir: Path) -> str:
    name = profile_dir.name.strip()
    return name or str(profile_dir)


def system_prompt_path(log_dir: Path | None) -> Path | None:
    return log_dir / SYSTEM_PROMPT_FILE_NAME if log_dir else None


def system_prompt_history_path(log_dir: Path | None) -> Path | None:
    return log_dir / SYSTEM_PROMPT_HISTORY_FILE_NAME if log_dir else None


def conversation_path(log_dir: Path | None) -> Path | None:
    return log_dir / CONVERSATION_FILE_NAME if log_dir else None
