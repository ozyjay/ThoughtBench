"""Assistant behaviour editing and rewrite mixin."""

import re
import sys
import threading
import traceback
import tkinter as tk

from .knowledge import (
    DEFAULT_KNOWLEDGE_SETTINGS,
    format_diagnostic_summary,
    format_retrieved_context,
    format_source_summary,
    index_is_stale,
)
from .model_loading import model_input_device
from .model import split_model_response
from .config import get_model_option


class BehaviourMixin:
    def _reset_conversation(self):
        self.messages = []

    def _get_system_prompt(self) -> str:
        return self.system_prompt.get("1.0", tk.END).strip()

    def _fit_system_prompt_to_content(self):
        line_count = int(self.system_prompt.index("end-1c").split(".")[0])
        self.system_prompt_lines.set(line_count)
        self._apply_system_prompt_height()

    def _apply_system_prompt_height(self):
        try:
            requested = int(self.system_prompt_lines.get())
        except (tk.TclError, ValueError):
            requested = self._system_prompt_min_lines

        height = max(self._system_prompt_min_lines, min(self._system_prompt_max_lines, requested))
        try:
            current = int(self.system_prompt_lines.get())
        except (tk.TclError, ValueError):
            current = None
        if current != height:
            self.system_prompt_lines.set(height)
        if int(self.system_prompt.cget("height")) != height:
            self.system_prompt.configure(height=height)

    def _set_system_prompt(self, text: str):
        self._remember_system_prompt_version(self._get_system_prompt(), "before rewrite", force=True)
        self.system_prompt.delete("1.0", tk.END)
        self.system_prompt.insert("1.0", text)
        self._fit_system_prompt_to_content()
        self.system_prompt.see(tk.END)
        self.system_prompt.edit_reset()
        self.system_prompt.edit_modified(False)
        self._save_system_prompt(remember_previous=False)
        self._schedule_token_usage_update()

    def _start_behaviour_rewrite(self, advice: str):
        advice = advice.strip()
        if not advice:
            self.status_var.set("Type a behaviour change first.")
            return

        if self.model is None or self.processor is None:
            self.status_var.set("Wait for the model to finish loading before updating behaviour.")
            return

        if self.generating:
            self.status_var.set("Stop the current generation before updating behaviour.")
            return

        if self.updating_behaviour:
            self.status_var.set("Behaviour update already in progress.")
            return

        self.updating_behaviour = True
        self.behaviour_btn.configure(state=tk.DISABLED)
        self._refresh_send_button_state()
        self.status_var.set("Rewriting assistant behaviour...")
        self._append_chat("System: ", "system_msg")
        self._append_chat(f"Rewriting assistant behaviour from advice: {advice}\n\n", "system_msg")
        self._append_log_entry("Behaviour Rewrite Advice", advice)
        self._reset_thinking_panel_for_generation()
        if self.think_var.get():
            self._begin_thinking_block()
        current_behaviour = self._get_system_prompt()
        threading.Thread(
            target=self._rewrite_behaviour,
            args=(current_behaviour, advice),
            daemon=True,
        ).start()

    def _rewrite_behaviour(self, current_behaviour: str, advice: str):
        import torch

        rewrite_messages = [
            {
                "role": "system",
                "content": (
                    "You are a careful prompt editor. Rewrite assistant behaviour "
                    "instructions for a chat application. Preserve useful existing "
                    "requirements, incorporate the user's requested change, remove "
                    "contradictions and obsolete wording, and return only the complete "
                    "replacement behaviour instructions. Do not explain your changes."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Current assistant behaviour instructions:\n"
                    "```text\n"
                    f"{current_behaviour or 'You are a helpful assistant.'}\n"
                    "```\n\n"
                    "Requested behaviour change:\n"
                    "```text\n"
                    f"{advice}\n"
                    "```\n\n"
                    "Return the complete replacement Assistant Behaviour text only."
                ),
            },
        ]

        try:
            prompt = self.processor.apply_chat_template(
                rewrite_messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=True,
            )
            inputs = self.processor(text=prompt, return_tensors="pt").to(model_input_device(self.model))
            input_length = inputs["input_ids"].shape[-1]
            with torch.inference_mode():
                output_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=1024,
                    do_sample=False,
                )
            new_tokens = output_ids[:, input_length:]
            raw_text = self.processor.tokenizer.decode(
                new_tokens[0],
                skip_special_tokens=False,
            )
            model_option = get_model_option(getattr(self, "selected_model_id", None))
            parsed = split_model_response(raw_text, model_option)
            thinking_text, response_text = parsed.thinking, parsed.content
            if thinking_text:
                thinking_text = thinking_text.replace("\\n", "\n")
            rewritten = self._clean_behaviour_rewrite(response_text or raw_text)
            if not rewritten:
                raise ValueError("The behaviour rewrite was empty.")

            self.root.after(
                0,
                lambda: self._finish_behaviour_rewrite(advice, rewritten, thinking_text),
            )
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            self.root.after(0, lambda err=exc: self._fail_behaviour_rewrite(err))

    def _clean_behaviour_rewrite(self, text: str) -> str:
        cleaned = text.replace("\\n", "\n").strip()
        cleaned = re.sub(r"<\|?channel\|?>\s*\w*|<\w+\|>|<\|turn\>|<turn\|>", "", cleaned)
        cleaned = cleaned.strip()

        fence_match = re.fullmatch(r"```(?:text|markdown|md)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        return cleaned

    def _finish_behaviour_rewrite(self, advice: str, rewritten: str, thinking_text: str | None):
        if thinking_text and self.think_var.get():
            self._stream_thinking_text = thinking_text
            self._replace_streamed_thinking_with_markdown(thinking_text)
            self._append_log_entry("Thinking", thinking_text)
        else:
            self._discard_active_thinking_block()
            self._hide_thinking_panel()
        self._set_system_prompt(rewritten)
        self._append_chat("System: ", "system_msg")
        self._append_chat(
            "Assistant behaviour rewritten for future responses.\n\n",
            "system_msg",
        )
        self._append_log_entry("Behaviour Rewrite", f"Advice:\n{advice}\n\nUpdated behaviour:\n{rewritten}")
        self.status_var.set("Assistant behaviour rewritten for future responses.")
        self.updating_behaviour = False
        self.behaviour_btn.configure(state=tk.NORMAL)
        self._refresh_send_button_state()

    def _fail_behaviour_rewrite(self, error: Exception):
        self._discard_active_thinking_block()
        self._append_chat("System: ", "system_msg")
        self._append_chat(f"Behaviour rewrite failed: {error}\n\n", "system_msg")
        self._append_log_entry("Behaviour Rewrite Error", str(error))
        self.status_var.set("Behaviour rewrite failed.")
        self.updating_behaviour = False
        self.behaviour_btn.configure(state=tk.NORMAL)
        self._refresh_send_button_state()

    def _extract_behaviour_command(self, text: str) -> str | None:
        stripped = text.strip()
        lowered = stripped.lower()
        command = "/behaviour"
        if lowered == command:
            return ""
        if lowered.startswith(command + " "):
            return stripped[len(command):].strip()
        return None

    def _highlight_user_input_commands(self):
        self.user_input.tag_remove("slash_command", "1.0", tk.END)
        self.user_input.tag_remove("slash_command_arg", "1.0", tk.END)

        text = self.user_input.get("1.0", "end-1c")
        match = re.match(r"^(/(?:behaviour|think|reset))(\s+.*)?$", text, re.IGNORECASE | re.DOTALL)
        if not match:
            return

        command_end = len(match.group(1))
        self.user_input.tag_add("slash_command", "1.0", f"1.0+{command_end}c")
        if match.group(2):
            self.user_input.tag_add("slash_command_arg", f"1.0+{command_end}c", tk.END)

    def _on_user_input_changed(self, _event=None):
        self.root.after_idle(self._highlight_user_input_commands)
        self.root.after_idle(self._update_slash_command_popup)

    def _slash_command_query(self) -> str | None:
        text = self.user_input.get("1.0", "end-1c")
        if "\n" in text or not text.startswith("/"):
            return None
        if " " in text:
            return None
        return text.lower()

    def _update_slash_command_popup(self):
        query = self._slash_command_query()
        if query is None:
            self._hide_slash_command_popup()
            return

        matches = [
            item for item in self._slash_commands
            if item[0].startswith(query)
        ]
        if not matches:
            self._hide_slash_command_popup()
            return

        self._slash_popup_items = matches
        self.slash_popup.delete(0, tk.END)
        for command, description in matches:
            self.slash_popup.insert(tk.END, f"{command} - {description}")
        self.slash_popup.selection_clear(0, tk.END)
        self.slash_popup.selection_set(0)
        self.slash_popup.activate(0)
        self.slash_popup.configure(height=min(5, len(matches)))

        if not self._slash_popup_visible:
            self.slash_popup.place(
                in_=self.user_input,
                x=0,
                y=0,
                relwidth=1,
                anchor=tk.SW,
            )
            self._slash_popup_visible = True

    def _hide_slash_command_popup(self, _event=None):
        if self._slash_popup_visible:
            self.slash_popup.place_forget()
            self._slash_popup_visible = False
        return None

    def _selected_slash_command_index(self) -> int:
        selection = self.slash_popup.curselection()
        if selection:
            return int(selection[0])
        return 0

    def _select_slash_command_index(self, index: int):
        if not self._slash_popup_items:
            return
        index = max(0, min(index, len(self._slash_popup_items) - 1))
        self.slash_popup.selection_clear(0, tk.END)
        self.slash_popup.selection_set(index)
        self.slash_popup.activate(index)
        self.slash_popup.see(index)

    def _slash_command_down(self, _event=None):
        if not self._slash_popup_visible:
            return None
        self._select_slash_command_index(self._selected_slash_command_index() + 1)
        return "break"

    def _slash_command_up(self, _event=None):
        if not self._slash_popup_visible:
            return None
        self._select_slash_command_index(self._selected_slash_command_index() - 1)
        return "break"

    def _complete_selected_slash_command(self, _event=None):
        if not self._slash_popup_visible or not self._slash_popup_items:
            return None

        command, _description = self._slash_popup_items[self._selected_slash_command_index()]
        suffix = " " if command == "/behaviour" else ""
        self.user_input.delete("1.0", tk.END)
        self.user_input.insert("1.0", command + suffix)
        self.user_input.mark_set(tk.INSERT, tk.END)
        self._hide_slash_command_popup()
        self._highlight_user_input_commands()
        return "break"

    def _knowledge_context_for_latest_user_message(self, log_retrieval: bool = True) -> str:
        self.last_retrieved_knowledge = []
        knowledge_index = getattr(self, "knowledge_index", None)
        if knowledge_index is None or not getattr(knowledge_index, "chunks", None):
            return ""

        settings = getattr(self, "knowledge_settings", DEFAULT_KNOWLEDGE_SETTINGS)
        if getattr(self, "log_dir", None) and index_is_stale(self.log_dir, knowledge_index, settings):
            self.knowledge_index_stale = True
            warning = "Knowledge index is stale - rebuild recommended."
            if hasattr(self, "status_var"):
                self.status_var.set(warning)
            self._append_log_entry("Knowledge", warning)
            if hasattr(self, "_capture_diagnostic"):
                self._capture_diagnostic(warning + "\n", "diagnostic_meta")
            return ""

        latest_user_message = None
        for message in reversed(self.messages):
            if message.get("role") == "user":
                latest_user_message = message.get("content")
                break
        if not isinstance(latest_user_message, str) or not latest_user_message.strip():
            return ""

        results = knowledge_index.retrieve(
            latest_user_message,
            top_k=settings.top_k,
            minimum_score=settings.minimum_score,
            minimum_matched_terms=settings.minimum_matched_terms,
        )
        self.last_retrieved_knowledge = results
        if results and log_retrieval:
            self._append_log_entry(
                "Knowledge",
                format_source_summary(results),
            )
            if hasattr(self, "_capture_diagnostic"):
                self._capture_diagnostic(format_diagnostic_summary(results), "diagnostic_meta")
        return format_retrieved_context(results, max_chars=settings.context_char_budget)

    def _build_messages(self, log_knowledge: bool = True) -> list[dict]:
        self._save_system_prompt()
        messages = [{"role": "system", "content": self._get_system_prompt()}] + list(self.messages)
        knowledge_context = self._knowledge_context_for_latest_user_message(log_knowledge)
        if not knowledge_context:
            return messages

        insert_at = len(messages)
        if len(messages) > 1 and messages[-1].get("role") == "user":
            insert_at = len(messages) - 1
        messages.insert(insert_at, {"role": "system", "content": knowledge_context})
        return messages

