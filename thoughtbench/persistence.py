"""Conversation, settings, and transcript persistence mixin."""

import json
import re
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .config import (
    APP_NAME,
    APP_FOLDER_NAME,
    SYSTEM_PROMPT_HISTORY_LIMIT,
    get_model_option,
    valid_model_id_or_default,
)
from .storage import (
    conversation_path,
    default_profiles_root,
    legacy_profile_roots,
    profile_label,
    read_settings,
    system_prompt_history_path,
    system_prompt_path,
    write_settings,
)


class PersistenceMixin:
    def _setup_logging(self):
        self.log_dir = self._resolve_log_dir()
        if not self.log_dir:
            self.status_var.set("Logging disabled: no transcript folder selected.")
            return

        self._load_saved_system_prompt()
        self._load_system_prompt_history()
        self._save_system_prompt(remember_previous=False)
        self._start_new_log()

    def _read_settings(self) -> dict:
        return read_settings()

    def _write_settings(self, settings: dict):
        write_settings(settings)

    def _read_selected_model_id(self) -> str:
        return valid_model_id_or_default(self._read_settings().get("selected_model_id"))

    def _save_selected_model_id(self, model_id: str):
        settings = self._read_settings()
        settings["selected_model_id"] = valid_model_id_or_default(model_id)
        self._write_settings(settings)

    def _profile_label(self, profile_dir: Path) -> str:
        return profile_label(profile_dir)

    def _read_profiles_root(self) -> Path:
        raw_path = self._read_settings().get("profiles_root")
        if isinstance(raw_path, str) and raw_path.strip():
            return Path(raw_path).expanduser()

        return default_profiles_root()

    def _save_profiles_root(self, profiles_root: Path):
        settings = self._read_settings()
        settings["profiles_root"] = str(profiles_root.resolve())
        self._write_settings(settings)

    def _read_active_profile_dir(self) -> Path | None:
        raw_path = self._read_settings().get("active_profile_dir")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None

        path = Path(raw_path).expanduser()
        return path if path.exists() and path.is_dir() else None

    def _read_recent_profile_dirs(self) -> list[Path]:
        settings = self._read_settings()
        raw_dirs = settings.get("recent_profile_dirs")
        if not isinstance(raw_dirs, list):
            raw_dirs = []

        profile_dirs: list[Path] = []
        for raw_path in raw_dirs:
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            path = Path(raw_path).expanduser()
            if path.exists() and path.is_dir() and path not in profile_dirs:
                profile_dirs.append(path)

        return profile_dirs

    def _save_active_profile_dir(self, profile_dir: Path):
        resolved = profile_dir.resolve()
        settings = self._read_settings()
        settings["active_profile_dir"] = str(resolved)
        recent = [resolved]
        for path in self._read_recent_profile_dirs():
            if path.resolve() != resolved:
                recent.append(path.resolve())
        settings["recent_profile_dirs"] = [str(path) for path in recent[:12]]
        settings.pop("log_dir", None)
        self._write_settings(settings)
        self._refresh_profile_menu()

    def _refresh_profile_menu(self):
        combo = getattr(self, "profile_combo", None)
        if combo is None:
            return

        profile_dirs = self._read_recent_profile_dirs()
        if self.log_dir and self.log_dir.exists() and self.log_dir not in profile_dirs:
            profile_dirs.insert(0, self.log_dir)

        name_counts: dict[str, int] = {}
        for path in profile_dirs:
            name_counts[self._profile_label(path)] = name_counts.get(self._profile_label(path), 0) + 1

        labels: list[str] = []
        self._profile_label_to_dir = {}
        for path in profile_dirs:
            label = self._profile_label(path)
            if name_counts[label] > 1:
                label = str(path)
            labels.append(label)
            self._profile_label_to_dir[label] = path

        combo.configure(values=labels, state="readonly" if labels else tk.DISABLED)
        if self.log_dir:
            current_label = self._profile_label(self.log_dir)
            if name_counts.get(current_label, 0) > 1:
                current_label = str(self.log_dir)
            self.profile_var.set(current_label)
        elif labels:
            self.profile_var.set(labels[0])
        else:
            self.profile_var.set("No profiles")

    def _sanitize_profile_name(self, name: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name.strip())
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return cleaned or "New Profile"

    def _ensure_profile_dir(self, profile_dir: Path) -> bool:
        try:
            profile_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Behaviour Profile",
                f"Could not create profile folder:\n{profile_dir}\n\n{exc}",
                parent=self.root,
            )
            return False

        prompt_path = system_prompt_path(profile_dir)
        if prompt_path and not prompt_path.exists():
            try:
                prompt_path.write_text(
                    self._get_system_prompt() or "You are a helpful assistant.",
                    encoding="utf-8",
                )
            except OSError as exc:
                messagebox.showerror(
                    "Behaviour Profile",
                    f"Could not initialize profile prompt:\n{prompt_path}\n\n{exc}",
                    parent=self.root,
                )
                return False

        return True

    def _load_saved_system_prompt(self):
        saved_prompt = None
        prompt_path = self._system_prompt_path()
        if prompt_path and prompt_path.exists():
            try:
                saved_prompt = prompt_path.read_text(encoding="utf-8")
            except OSError:
                saved_prompt = None

        settings = self._read_settings()
        old_saved_prompt = settings.get("system_prompt")
        if saved_prompt is None and isinstance(old_saved_prompt, str):
            saved_prompt = old_saved_prompt

        if "system_prompt" in settings:
            settings.pop("system_prompt", None)
            self._write_settings(settings)

        if not isinstance(saved_prompt, str):
            return

        self.system_prompt.delete("1.0", tk.END)
        self.system_prompt.insert("1.0", saved_prompt)
        self._fit_system_prompt_to_content()
        self.system_prompt.edit_reset()
        self.system_prompt.edit_modified(False)

    def _on_system_prompt_modified(self, _event=None):
        if not self.system_prompt.edit_modified():
            return

        self.system_prompt.edit_modified(False)
        if self._system_prompt_save_job:
            self.root.after_cancel(self._system_prompt_save_job)
        self._system_prompt_save_job = self.root.after(500, self._save_system_prompt)
        self._schedule_token_usage_update()

    def _save_system_prompt(self, remember_previous: bool = True, history_source: str = "edited"):
        self._system_prompt_save_job = None
        prompt_path = self._system_prompt_path()
        if not prompt_path:
            return

        current_prompt = self._get_system_prompt()
        if remember_previous and prompt_path.exists():
            try:
                previous_prompt = prompt_path.read_text(encoding="utf-8")
            except OSError:
                previous_prompt = ""
            if previous_prompt.strip() and previous_prompt != current_prompt:
                self._remember_system_prompt_version(previous_prompt, history_source)

        try:
            prompt_path.write_text(current_prompt, encoding="utf-8")
        except OSError as exc:
            self.status_var.set(f"System prompt save failed: {exc}")

    def _system_prompt_path(self) -> Path | None:
        if not self.log_dir:
            return None

        return system_prompt_path(self.log_dir)

    def _system_prompt_history_path(self) -> Path | None:
        if not self.log_dir:
            return None

        return system_prompt_history_path(self.log_dir)

    def _load_system_prompt_history(self):
        self._system_prompt_history = []
        path = self._system_prompt_history_path()
        if not path or not path.exists():
            self._refresh_system_prompt_history_menu()
            return

        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._refresh_system_prompt_history_menu()
            return

        if not isinstance(loaded, list):
            self._refresh_system_prompt_history_menu()
            return

        history: list[dict] = []
        for item in loaded:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            timestamp = item.get("timestamp")
            source = item.get("source", "edited")
            if not isinstance(content, str) or not content.strip():
                continue
            if not isinstance(timestamp, str):
                timestamp = ""
            if not isinstance(source, str):
                source = "edited"
            history.append(
                {
                    "timestamp": timestamp,
                    "source": source,
                    "content": content,
                }
            )

        self._system_prompt_history = history[:SYSTEM_PROMPT_HISTORY_LIMIT]
        self._refresh_system_prompt_history_menu()

    def _write_system_prompt_history(self):
        path = self._system_prompt_history_path()
        if not path:
            return

        try:
            path.write_text(
                json.dumps(
                    self._system_prompt_history[:SYSTEM_PROMPT_HISTORY_LIMIT],
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            self.status_var.set(f"System prompt history save failed: {exc}")

    def _remember_system_prompt_version(self, content: str, source: str = "edited", force: bool = False):
        content = content.strip()
        if not content:
            return
        if not force and content == self._get_system_prompt():
            return
        if any(entry.get("content") == content for entry in self._system_prompt_history):
            return

        self._system_prompt_history.insert(
            0,
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "source": source,
                "content": content,
            },
        )
        self._system_prompt_history = self._system_prompt_history[:SYSTEM_PROMPT_HISTORY_LIMIT]
        self._write_system_prompt_history()
        self._refresh_system_prompt_history_menu()

    def _refresh_system_prompt_history_menu(self):
        history_combo = getattr(self, "system_prompt_history_combo", None)
        restore_button = getattr(self, "restore_system_prompt_btn", None)
        if history_combo is None or restore_button is None:
            return

        self._system_prompt_history_labels = [
            self._system_prompt_history_label(entry)
            for entry in self._system_prompt_history
        ]
        history_combo.configure(values=self._system_prompt_history_labels)
        has_history = bool(self._system_prompt_history_labels)
        history_combo.configure(state="readonly" if has_history else tk.DISABLED)
        restore_button.configure(state=tk.NORMAL if has_history else tk.DISABLED)
        if not has_history:
            self.system_prompt_history_var.set("No saved prompts")
        elif self.system_prompt_history_var.get() not in self._system_prompt_history_labels:
            self.system_prompt_history_var.set("Prompt history")

    def _system_prompt_history_label(self, entry: dict) -> str:
        timestamp = entry.get("timestamp") or "unknown time"
        source = entry.get("source") or "edited"
        preview = self._system_prompt_history_preview(entry.get("content") or "")
        return f"{timestamp} - {source} - {preview}"

    def _system_prompt_history_preview(self, content: str) -> str:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return "(empty)"

        first_line = self._truncate_prompt_history_line(lines[0], 38)
        if len(lines) == 1:
            return first_line

        last_line = self._truncate_prompt_history_line(lines[-1], 48)
        if last_line == first_line:
            return first_line

        return f"{first_line} ... {last_line}"

    @staticmethod
    def _truncate_prompt_history_line(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    def _restore_selected_system_prompt(self):
        label = self.system_prompt_history_var.get()
        try:
            index = self._system_prompt_history_labels.index(label)
        except ValueError:
            self.status_var.set("Choose a saved prompt first.")
            return

        entry = self._system_prompt_history[index]
        content = entry.get("content")
        if not isinstance(content, str):
            self.status_var.set("Saved prompt could not be restored.")
            return

        self._remember_system_prompt_version(self._get_system_prompt(), "before restore", force=True)
        self.system_prompt.delete("1.0", tk.END)
        self.system_prompt.insert("1.0", content)
        self._fit_system_prompt_to_content()
        self.system_prompt.see("1.0")
        self.system_prompt.edit_reset()
        self.system_prompt.edit_modified(False)
        self._save_system_prompt(remember_previous=False)
        self.status_var.set("Restored saved assistant behaviour.")
        self._schedule_token_usage_update()

    def _conversation_path(self) -> Path | None:
        if not self.log_dir:
            return None

        return conversation_path(self.log_dir)

    def _load_saved_conversation(self):
        path = self._conversation_path()
        if not path or not path.exists():
            self.messages = []
            return

        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.messages = []
            return

        if not isinstance(loaded, list):
            self.messages = []
            return

        messages: list[dict] = []
        for item in loaded:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                message = {"role": role, "content": content}
                if not messages or messages[-1] != message:
                    messages.append(message)

        self.messages = messages
        self._render_saved_conversation()
        self._schedule_token_usage_update()

    def _save_conversation(self):
        path = self._conversation_path()
        if not path:
            return

        compacted: list[dict] = []
        for message in self.messages:
            if compacted and compacted[-1] == message:
                continue
            compacted.append(message)
        if len(compacted) != len(self.messages):
            self.messages = compacted

        try:
            path.write_text(
                json.dumps(self.messages, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            self.status_var.set(f"Conversation save failed: {exc}")

    def _render_saved_conversation(self):
        if not self.messages:
            return

        self._append_chat("System: ", "system_msg")
        self._append_chat("Restored previous conversation.\n\n", "system_msg")
        for message in self.messages:
            role = message["role"]
            content = message["content"]
            if role == "user":
                self._append_chat("You: ", "user")
                self._append_chat(f"{content}\n\n")
            elif role == "assistant":
                self._append_chat(self._assistant_label(), "assistant")
                self._append_markdown(content)
                self._append_chat("\n\n")
        self.root.after_idle(lambda: self.chat_display.see(tk.END))

    def _resolve_log_dir(self) -> Path | None:
        active_profile = self._read_active_profile_dir()
        if active_profile:
            self._save_active_profile_dir(active_profile)
            return active_profile

        legacy_profile = self._read_configured_log_dir()
        if legacy_profile:
            self._save_active_profile_dir(legacy_profile)
            return legacy_profile

        for candidate in (
            Path.home() / APP_FOLDER_NAME,
            *legacy_profile_roots(),
        ):
            if candidate.exists() and candidate.is_dir():
                self._save_active_profile_dir(candidate)
                return candidate

        parent = filedialog.askdirectory(
            parent=self.root,
            title=f"Choose where to create {APP_FOLDER_NAME}",
            mustexist=True,
        )
        if not parent:
            messagebox.showwarning(
                "Behaviour Profile",
                "No profile folder was selected. Conversation logging is disabled for this session.",
                parent=self.root,
            )
            return None

        log_dir = Path(parent) / APP_FOLDER_NAME
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                "Behaviour Profile",
                f"Could not create profile folder:\n{log_dir}\n\n{exc}",
                parent=self.root,
            )
            return None

        self._save_active_profile_dir(log_dir)
        return log_dir

    def _read_configured_log_dir(self) -> Path | None:
        raw_path = self._read_settings().get("log_dir")
        if not raw_path:
            return None

        path = Path(raw_path).expanduser()
        return path if path.exists() and path.is_dir() else None

    def _save_configured_log_dir(self, log_dir: Path):
        settings = self._read_settings()
        settings["log_dir"] = str(log_dir.resolve())
        self._write_settings(settings)

    def _on_profile_selected(self, _event=None):
        label = self.profile_var.get()
        profile_dir = self._profile_label_to_dir.get(label)
        if not profile_dir:
            return

        if self.log_dir and profile_dir.resolve() == self.log_dir.resolve():
            return

        self._switch_profile(profile_dir)

    def _on_new_profile(self):
        if self.generating or self.updating_behaviour:
            self.status_var.set("Stop generation or behaviour update before switching profiles.")
            return

        name = simpledialog.askstring(
            "New Behaviour Profile",
            "Profile name:",
            parent=self.root,
        )
        if name is None:
            return

        profile_name = self._sanitize_profile_name(name)
        profiles_root = self._read_profiles_root()
        self._save_profiles_root(profiles_root)
        profile_dir = profiles_root / profile_name
        counter = 2
        while profile_dir.exists():
            profile_dir = profiles_root / f"{profile_name} {counter}"
            counter += 1

        if not self._ensure_profile_dir(profile_dir):
            return

        conversation = conversation_path(profile_dir)
        if conversation and not conversation.exists():
            try:
                conversation.write_text("[]", encoding="utf-8")
            except OSError as exc:
                self.status_var.set(f"Profile conversation init failed: {exc}")

        self._switch_profile(profile_dir)

    def _on_add_existing_profile(self):
        if self.generating or self.updating_behaviour:
            self.status_var.set("Stop generation or behaviour update before switching profiles.")
            return

        selected = filedialog.askdirectory(
            parent=self.root,
            title="Choose behaviour profile folder",
            mustexist=True,
        )
        if not selected:
            return

        profile_dir = Path(selected)
        if not self._ensure_profile_dir(profile_dir):
            return

        self._switch_profile(profile_dir)

    def _switch_profile(self, profile_dir: Path):
        if self.generating or self.updating_behaviour:
            self.status_var.set("Stop generation or behaviour update before switching profiles.")
            self._refresh_profile_menu()
            return

        if self._system_prompt_save_job:
            try:
                self.root.after_cancel(self._system_prompt_save_job)
            except tk.TclError:
                pass
            self._system_prompt_save_job = None
        self._save_system_prompt()
        self._save_conversation()
        self._close_diagnostics_log()

        self.log_dir = profile_dir
        self.log_path = None
        self._save_active_profile_dir(profile_dir)

        self._cancel_stream_render_jobs()
        self._stream_response_text = ""
        self._stream_thinking_text = ""
        self._stream_response_pending_newline = False
        self._response_stream.reset()
        self._thinking_stream.reset()
        self.chat_display.configure(state=tk.NORMAL)
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.configure(state=tk.NORMAL)
        self.thinking_display.configure(state=tk.NORMAL)
        self.thinking_display.delete("1.0", tk.END)
        self.thinking_display.configure(state=tk.NORMAL)
        self._has_thinking_history = False
        self._active_thinking_block = False
        self._hide_thinking_panel()

        self._load_saved_system_prompt()
        self._load_system_prompt_history()
        self._load_saved_conversation()
        self._start_new_log()
        self._start_diagnostics_log()
        self._schedule_token_usage_update()
        self._capture_diagnostic(
            f"Switched profile: {profile_dir}\n",
            "diagnostic_meta",
        )
        self.status_var.set(f"Behaviour profile: {self._profile_label(profile_dir)}")

    def _start_new_log(self):
        if not self.log_dir:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = self.log_dir / f"gemma4_chat_{timestamp}.md"
        counter = 2
        while self.log_path.exists():
            self.log_path = self.log_dir / f"gemma4_chat_{timestamp}_{counter}.md"
            counter += 1
        model_option = get_model_option(getattr(self, "selected_model_id", None))
        header = (
            f"# {APP_NAME} Chat Log\n\n"
            f"Started: {datetime.now().isoformat(timespec='seconds')}\n\n"
            f"Model: {model_option.display_name} (`{model_option.model_id}`)\n\n"
            "## Assistant Behaviour\n\n"
            f"{self._get_system_prompt() or '(empty)'}\n\n"
            "---\n\n"
        )
        self._append_log_text(header)

    def _append_log_text(self, text: str):
        if not self.log_path:
            return

        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as exc:
            self.log_path = None
            self.status_var.set(f"Logging disabled: {exc}")

    def _append_log_entry(self, role: str, content: str):
        if not content:
            return

        timestamp = datetime.now().isoformat(timespec="seconds")
        self._append_log_text(f"## {role} - {timestamp}\n\n{content.strip()}\n\n")

    def _append_generation_settings_log(self, enable_thinking: bool):
        settings = (
            f"Thinking Mode: {'on' if enable_thinking else 'off'}\n\n"
            f"Temperature: {self.temp_var.get()}\n\n"
            f"Top-p: {self.top_p_var.get()}\n\n"
            f"Top-k: {self.top_k_var.get()}\n\n"
            f"Max tokens: {self.max_tokens_var.get()}\n\n"
            f"Assistant Behaviour:\n\n{self._get_system_prompt() or '(empty)'}"
        )
        self._append_log_entry("Generation Settings", settings)

