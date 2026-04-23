"""Model loading, generation, timers, and lifecycle mixin."""

import sys
import threading
import time
import traceback
import tkinter as tk
from datetime import datetime

from .config import APP_NAME, get_model_option
from .model_loading import load_processor_and_model, model_input_device
from .model import _StopOnEvent, split_model_response, strip_chat_special_tokens
from .stats import TkProgressBar


class RuntimeMixin:
    def _start_stats_loop(self):
        self._refresh_stats_text()
        self.root.after(2000, self._start_stats_loop)

    def _refresh_stats_text(self):
        hardware_text = self.stats.get() if self.stats is not None else "CPU: loading"
        self.stats_var.set(hardware_text)
        self._apply_token_usage_style()

    def _apply_token_usage_style(self):
        style_name = {
            "warning": "StatsWarning.TLabel",
            "critical": "StatsCritical.TLabel",
        }.get(self._token_usage_state, "Stats.TLabel")
        if getattr(self, "token_stats_label", None) is not None:
            self.token_stats_label.configure(style=style_name)

    def _discover_context_limit(self, fallback: int) -> int:
        candidates: list[int] = []
        tokenizer = getattr(self.processor, "tokenizer", None)
        for obj in (tokenizer, getattr(self.model, "config", None)):
            if obj is None:
                continue
            for attr in (
                "model_max_length",
                "max_position_embeddings",
                "max_sequence_length",
                "seq_length",
            ):
                value = getattr(obj, attr, None)
                if isinstance(value, int) and 0 < value < 1_000_000:
                    candidates.append(value)

        config = getattr(self.model, "config", None)
        for child_name in ("text_config", "language_config"):
            child = getattr(config, child_name, None) if config is not None else None
            if child is None:
                continue
            for attr in ("max_position_embeddings", "max_sequence_length", "seq_length"):
                value = getattr(child, attr, None)
                if isinstance(value, int) and 0 < value < 1_000_000:
                    candidates.append(value)

        if candidates:
            return max(candidates)

        return fallback or 8192

    def _format_token_usage(
        self,
        prompt_tokens: int,
        reserved_tokens: int,
        context_limit: int,
        live_reply_tokens: int = 0,
    ) -> tuple[str, str, bool]:
        reply_window_tokens = max(reserved_tokens, live_reply_tokens)
        used_tokens = prompt_tokens + reply_window_tokens
        pct = (used_tokens / context_limit) * 100 if context_limit else 0
        prompt_over_limit = prompt_tokens >= context_limit
        if prompt_over_limit or pct >= 95:
            state = "critical"
        elif pct >= 80:
            state = "warning"
        else:
            state = "normal"

        if live_reply_tokens:
            reply_text = f"reply {live_reply_tokens:,}/{reserved_tokens:,}"
        else:
            reply_text = f"reply budget {reserved_tokens:,}"

        text = (
            f"Tokens: {used_tokens:,}/{context_limit:,} ({pct:.0f}%)"
            f" - input {prompt_tokens:,} + {reply_text}"
        )
        return text, state, prompt_over_limit

    def _schedule_token_usage_update(self):
        if getattr(self, "_token_update_job", None):
            try:
                self.root.after_cancel(self._token_update_job)
            except tk.TclError:
                pass
        self._token_update_job = self.root.after(150, self._update_token_usage_async)

    def _schedule_live_token_usage_update(self):
        if getattr(self, "_token_update_job", None):
            return

        self._token_update_job = self.root.after(750, self._update_token_usage_async)

    def _update_token_usage_async(self):
        self._token_update_job = None
        if self.processor is None or self.model is None:
            self.token_usage_var.set("Tokens: loading")
            self._token_usage_state = "loading"
            self._token_prompt_over_limit = False
            self._apply_token_usage_style()
            return

        self._token_update_revision += 1
        revision = self._token_update_revision
        messages = [{"role": "system", "content": self._get_system_prompt()}] + list(self.messages)
        live_response_text = self._stream_response_text if self.generating else ""
        enable_thinking = bool(self.think_var.get()) and get_model_option(
            getattr(self, "selected_model_id", None)
        ).supports_thinking
        try:
            reserved_tokens = int(self.max_tokens_var.get())
        except (tk.TclError, ValueError):
            reserved_tokens = 0

        def _count():
            try:
                text = self.processor.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=enable_thinking,
                )
                tokenizer = self.processor.tokenizer
                encoded = tokenizer(text, add_special_tokens=False)
                prompt_tokens = len(encoded["input_ids"])
                if live_response_text.strip():
                    live_encoded = tokenizer(live_response_text, add_special_tokens=False)
                    live_reply_tokens = len(live_encoded["input_ids"])
                else:
                    live_reply_tokens = 0
                context_limit = self._discover_context_limit(max(reserved_tokens, 8192))
                token_text, state, prompt_over_limit = self._format_token_usage(
                    prompt_tokens,
                    reserved_tokens,
                    context_limit,
                    live_reply_tokens,
                )
                self.root.after(
                    0,
                    lambda: self._finish_token_usage_update(
                        revision,
                        prompt_tokens,
                        reserved_tokens,
                        context_limit,
                        token_text,
                        state,
                        prompt_over_limit,
                    ),
                )
            except Exception as exc:
                self.root.after(0, lambda err=exc: self._fail_token_usage_update(revision, err))

        threading.Thread(target=_count, daemon=True).start()

    def _finish_token_usage_update(
        self,
        revision: int,
        prompt_tokens: int,
        reserved_tokens: int,
        context_limit: int,
        token_text: str,
        state: str,
        prompt_over_limit: bool,
    ):
        if revision != self._token_update_revision:
            return

        self._token_prompt_tokens = prompt_tokens
        self._token_reserved_tokens = reserved_tokens
        self._token_context_limit = context_limit
        self._token_usage_pct = ((prompt_tokens + reserved_tokens) / context_limit) * 100
        self._token_usage_state = state
        self._token_prompt_over_limit = prompt_over_limit
        self.token_usage_var.set(token_text)
        self._refresh_stats_text()
        self._refresh_send_button_state()

    def _fail_token_usage_update(self, revision: int, error: Exception):
        if revision != self._token_update_revision:
            return

        self.token_usage_var.set("Tokens: unavailable")
        self._token_usage_state = "warning"
        self._token_prompt_over_limit = False
        self._apply_token_usage_style()
        self._capture_diagnostic(f"Token count unavailable: {error}\n", "diagnostic_meta")

    def _refresh_send_button_state(self):
        self._refresh_generation_slider_state()
        think_check = getattr(self, "think_check", None)
        if think_check is not None:
            supports_thinking = get_model_option(
                getattr(self, "selected_model_id", None)
            ).supports_thinking
            think_check.configure(
                state=(
                    tk.DISABLED
                    if self.generating or self.updating_behaviour or not supports_thinking
                    else tk.NORMAL
                )
            )
        if self.generating:
            self.send_btn.configure(state=tk.NORMAL, text="Stop")
            return

        if self.updating_behaviour or self.model is None or self._pending_send:
            self.send_btn.configure(state=tk.DISABLED)
            return

        if self._token_prompt_over_limit:
            self.send_btn.configure(state=tk.DISABLED)
            return

        self.send_btn.configure(state=tk.NORMAL, text="Send")

    # ── Elapsed time tracker ────────────────────────────────────────────

    def _start_elapsed_timer(self):
        self._load_start = time.perf_counter()
        self._tick_elapsed()

    def _tick_elapsed(self):
        if self._load_start > 0:
            elapsed = time.perf_counter() - self._load_start
            self.elapsed_var.set(f"{elapsed:.0f}s")
            self.root.after(500, self._tick_elapsed)

    def _stop_elapsed_timer(self):
        self._load_start = 0

    # ── Model loading ───────────────────────────────────────────────────

    def _load_model_async(self):
        model_option = get_model_option(getattr(self, "selected_model_id", None))
        self.root.title(f"{APP_NAME} - {model_option.display_name}")
        self._hide_status_progress()

        def _load():
            try:
                from huggingface_hub import snapshot_download

                self.root.after(0, self._start_elapsed_timer)

                # Phase 1: download with progress
                TkProgressBar._tk_progress_var = self.progress_var
                TkProgressBar._tk_status_var = self.status_var
                TkProgressBar._tk_root = self.root
                self.root.after(
                    0,
                    lambda: self.status_var.set(
                        f"Downloading {model_option.display_name}..."
                    ),
                )
                local_path = snapshot_download(model_option.model_id, tqdm_class=TkProgressBar)

                # Phase 2: load weights
                self.root.after(
                    0,
                    lambda: self.status_var.set(
                        f"Loading {model_option.display_name} weights..."
                    ),
                )
                self.root.after(0, lambda: self.loading_progress.configure(mode="indeterminate"))
                self.root.after(0, lambda: self.loading_progress.start(15))

                self.processor, self.model, load_info = load_processor_and_model(
                    local_path,
                    model_option=model_option,
                )

                def _done():
                    self.active_model_option = model_option
                    self.loading_progress.stop()
                    self.loading_progress.configure(mode="determinate")
                    self.progress_var.set(100)
                    self._stop_elapsed_timer()
                    self._hide_loading_screen()
                    self.progress_var.set(0)
                    self._schedule_token_usage_update()
                    if self._pending_send:
                        self._pending_send = False
                        self.status_var.set(
                            f"{model_option.display_name} loaded ({load_info.detail}). Sending queued message..."
                        )
                        self._start_generate()
                    else:
                        self.status_var.set(
                            f"{model_option.display_name} loaded ({load_info.detail}). Ready to chat."
                        )
                        self._refresh_send_button_state()
                    self._append_log_entry(
                        "System",
                        (
                            f"Model loaded: {model_option.display_name} "
                            f"(`{model_option.model_id}`) with {load_info.detail}. "
                            "Type a message and press Send."
                        ),
                    )

                self.root.after(0, _done)

            except Exception as e:
                traceback.print_exc(file=sys.stderr)

                def _show_load_error(err=e):
                    self._stop_elapsed_timer()
                    self.loading_progress.stop()
                    self.loading_progress.configure(mode="determinate")
                    self.status_var.set(f"{model_option.display_name} load failed: {err}")
                    self._hide_loading_screen()
                    self._append_chat(
                        f"[Error] Failed to load {model_option.display_name}: {err}\n\n",
                        "system_msg",
                    )
                    self._append_log_entry(
                        "Error",
                        f"Failed to load {model_option.display_name} (`{model_option.model_id}`): {err}",
                    )

                self.root.after(0, _show_load_error)

        threading.Thread(target=_load, daemon=True).start()

    # ── Input handling ──────────────────────────────────────────────────

    def _on_enter(self, event):
        if not event.state & 0x1:  # Shift not held
            if self._slash_popup_visible:
                return self._complete_selected_slash_command(event)
            self._on_send()
            return "break"

    def _on_update_behaviour(self):
        instruction = self.user_input.get("1.0", tk.END).strip()
        command_instruction = self._extract_behaviour_command(instruction)
        if command_instruction is not None:
            instruction = command_instruction

        if not instruction:
            self.status_var.set("Type a behaviour change first.")
            return

        self.user_input.delete("1.0", tk.END)
        self._highlight_user_input_commands()
        self._start_behaviour_rewrite(instruction)

    def _on_send(self):
        user_text = self.user_input.get("1.0", tk.END).strip()

        if self.updating_behaviour:
            self.status_var.set("Wait for the behaviour rewrite to finish.")
            return

        behaviour_instruction = self._extract_behaviour_command(user_text)
        if behaviour_instruction is not None:
            if behaviour_instruction:
                self.user_input.delete("1.0", tk.END)
                self._highlight_user_input_commands()
                self._hide_slash_command_popup()
                self._start_behaviour_rewrite(behaviour_instruction)
            else:
                self.status_var.set("Usage: /behaviour <instruction>")
            return

        command = user_text.lower()
        if command == "/think":
            if self.generating:
                self.status_var.set("Stop the current generation before changing thinking mode.")
                return
            self.think_var.set(not self.think_var.get())
            self.user_input.delete("1.0", tk.END)
            self._highlight_user_input_commands()
            self._hide_slash_command_popup()
            self._on_thinking_mode_changed()
            return

        if command == "/reset":
            self.user_input.delete("1.0", tk.END)
            self._highlight_user_input_commands()
            self._hide_slash_command_popup()
            self._on_clear()
            return

        # If generating and no new text, treat as a stop request
        if self.generating and not user_text:
            self._stop_event.set()
            self.status_var.set("Stopping...")
            return

        # If generating with new text, steer: stop current, queue follow-up
        if self.generating and user_text:
            self._stop_event.set()
            self.user_input.delete("1.0", tk.END)
            self._highlight_user_input_commands()
            self._hide_slash_command_popup()
            # The _finalise callback in _generate will see _pending_steer
            # and automatically start a new generation.
            self._pending_steer = user_text
            self.status_var.set("Steering — stopping current generation...")
            return

        if not user_text:
            return

        if self._token_prompt_over_limit:
            self.status_var.set("Prompt exceeds the model context window.")
            return

        self.user_input.delete("1.0", tk.END)
        self._highlight_user_input_commands()
        self._hide_slash_command_popup()
        self._flush_pending_response_markdown()
        self._append_chat("You: ", "user")
        self._append_chat(f"{user_text}\n\n")

        self.messages.append({"role": "user", "content": user_text})
        self._save_conversation()
        self._append_log_entry("User", user_text)
        self._schedule_token_usage_update()

        if self.model is None:
            # Model still loading — queue message and show feedback
            self._pending_send = True
            self.send_btn.configure(state=tk.DISABLED)
            self.status_var.set("Message queued — waiting for model to finish loading...")
            return

        self._start_generate()

    def _start_generate(self):
        self.generating = True
        self._stop_event.clear()
        self._refresh_send_button_state()
        self.status_var.set("Generating...")
        self._show_status_progress()
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start(50)
        self._start_elapsed_timer()
        self._append_chat(self._assistant_label(), "assistant")
        self._append_generation_settings_log(self.think_var.get())
        self._cancel_stream_render_jobs()
        self._stream_response_text = ""
        self._stream_thinking_text = ""
        self._stream_response_pending_newline = False
        self._response_stream.reset()
        self._reset_thinking_panel_for_generation()
        if self.think_var.get():
            self._begin_thinking_block()
        # Place a mark right after the assistant label so we know exactly where
        # the streamed text starts for the final markdown re-render.
        self.chat_display.configure(state=tk.NORMAL)
        self.chat_display.mark_set("stream_start", "end-1c")
        self.chat_display.mark_gravity("stream_start", tk.LEFT)
        self.chat_display.mark_set("response_live_tail_start", "end-1c")
        self.chat_display.mark_gravity("response_live_tail_start", tk.LEFT)
        self.chat_display.configure(state=tk.NORMAL)
        threading.Thread(target=self._generate, daemon=True).start()

    def _generate(self):
        try:
            from transformers import TextIteratorStreamer

            full_messages = self._build_messages()
            model_option = get_model_option(getattr(self, "selected_model_id", None))
            enable_thinking = bool(self.think_var.get()) and model_option.supports_thinking

            text = self.processor.apply_chat_template(
                full_messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=enable_thinking,
            )
            inputs = self.processor(text=text, return_tensors="pt").to(model_input_device(self.model))

            streamer = TextIteratorStreamer(
                self.processor.tokenizer,
                skip_prompt=True,
                skip_special_tokens=False,
            )

            gen_kwargs = dict(
                **inputs,
                max_new_tokens=self.max_tokens_var.get(),
                temperature=self.temp_var.get(),
                top_p=self.top_p_var.get(),
                top_k=self.top_k_var.get(),
                do_sample=True,
                streamer=streamer,
                stopping_criteria=[_StopOnEvent(self._stop_event)],
            )

            # Run generate in its own thread so we can iterate the streamer
            gen_error: list[Exception] = []

            def _run_generate():
                try:
                    self.model.generate(**gen_kwargs)
                except Exception as exc:
                    gen_error.append(exc)
                    streamer.end()  # unblock the iterator

            threading.Thread(target=_run_generate, daemon=True).start()

            if model_option.thinking_parser == "qwen_think_tags":
                thought_markers = ("<think>",)
                response_markers = ("</think>",)
                turn_markers = (
                    "<|im_start|>assistant",
                    "<|im_start|>",
                    "<|im_end|>",
                    "<|endoftext|>",
                )
                in_thinking = enable_thinking
            else:
                # Gemma emits channel-style markers in thinking mode.
                thought_markers = (
                    "<|channel>thought",
                    "<|channel> thought",
                    "<|channel|>thought",
                    "<|channel|> thought",
                    "<thought|>",
                    "<|channel>thinking",
                    "<|channel> thinking",
                    "<|channel|>thinking",
                    "<|channel|> thinking",
                    "<thinking|>",
                    "<|channel>analysis",
                    "<|channel> analysis",
                    "<|channel|>analysis",
                    "<|channel|> analysis",
                    "<analysis|>",
                )
                response_markers = (
                    "<channel|>",
                    "<|channel>response",
                    "<|channel> response",
                    "<|channel|>response",
                    "<|channel|> response",
                    "<response|>",
                    "<|channel>final",
                    "<|channel> final",
                    "<|channel|>final",
                    "<|channel|> final",
                    "<final|>",
                    "<|channel>answer",
                    "<|channel> answer",
                    "<|channel|>answer",
                    "<|channel|> answer",
                    "<answer|>",
                )
                turn_markers = ("<turn|>", "<|turn>")
                # Some Gemma responses omit channel markers even when thinking is
                # enabled. Treat unmarked output as the final response; switch to
                # thinking only after an explicit thought/analysis marker.
                in_thinking = False
            special_tokens = tuple(
                sorted(
                    (*thought_markers, *response_markers, *turn_markers),
                    key=len,
                    reverse=True,
                )
            )

            thinking_chunks: list[str] = []
            response_chunks: list[str] = []
            raw_chunks: list[str] = []
            buffer = ""  # accumulates text to detect special tokens

            for chunk in streamer:
                if self._stop_event.is_set():
                    break

                raw_chunks.append(chunk)
                buffer += chunk

                # Process buffer: extract special tokens and route text
                while buffer:
                    # Check if buffer starts with any special token
                    matched_token = None
                    for st in special_tokens:
                        if buffer.startswith(st):
                            matched_token = st
                            break

                    if matched_token:
                        buffer = buffer[len(matched_token):]
                        if matched_token in thought_markers:
                            in_thinking = True
                        elif matched_token in response_markers:
                            in_thinking = False
                        elif matched_token in turn_markers:
                            in_thinking = False
                        continue

                    # Check if buffer could be the start of a special token
                    might_match = any(
                        st.startswith(buffer) and len(buffer) < len(st)
                        for st in special_tokens
                    )
                    if might_match:
                        break  # wait for more data

                    # Emit one character
                    ch = buffer[0]
                    buffer = buffer[1:]
                    if in_thinking:
                        thinking_chunks.append(ch)
                        self.root.after(0, self._stream_thinking_chunk, ch)
                    else:
                        response_chunks.append(ch)
                        self.root.after(0, self._stream_chunk, ch)

            if gen_error:
                raise gen_error[0]

            if buffer and not any(st.startswith(buffer) for st in special_tokens):
                if in_thinking:
                    thinking_chunks.append(buffer)
                    self.root.after(0, self._stream_thinking_chunk, buffer)
                else:
                    response_chunks.append(buffer)
                    self.root.after(0, self._stream_chunk, buffer)

            was_stopped = self._stop_event.is_set()
            parsed = split_model_response("".join(raw_chunks), model_option)
            split_thinking_text, split_response_text = parsed.thinking, parsed.content
            if model_option.thinking_parser == "qwen_think_tags" and split_thinking_text is None:
                thinking_text = None
            else:
                thinking_text = "".join(thinking_chunks).strip() or split_thinking_text
            response_text = "".join(response_chunks).strip()
            if not response_text and (not enable_thinking or split_thinking_text):
                response_text = split_response_text
            elif model_option.thinking_parser == "qwen_think_tags" and split_thinking_text is None:
                response_text = split_response_text

            if response_text:
                response_text = response_text.replace("\\n", "\n")
                response_text = split_model_response(response_text, model_option).content
            if thinking_text:
                thinking_text = thinking_text.replace("\\n", "\n")
                thinking_text = strip_chat_special_tokens(thinking_text)

            def _finalise():
                self._cancel_stream_render_jobs()
                # Replace the streamed plain text with properly rendered markdown
                self._replace_streamed_with_markdown(response_text)

                # Re-render thinking panel with markdown if we have thinking content
                if thinking_text:
                    self._replace_streamed_thinking_with_markdown(thinking_text)
                    self._append_log_entry("Thinking", thinking_text)
                else:
                    self._discard_active_thinking_block()

                if was_stopped and response_text:
                    # Save partial response with a marker
                    logged_response = response_text + " [interrupted]"
                    self.messages.append({"role": "assistant", "content": logged_response})
                    self._save_conversation()
                    self._append_log_entry("Assistant", logged_response)
                    self._schedule_token_usage_update()
                elif response_text:
                    self.messages.append({"role": "assistant", "content": response_text})
                    self._save_conversation()
                    self._append_log_entry("Assistant", response_text)
                    self._schedule_token_usage_update()

                self._stop_elapsed_timer()
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
                self.progress_var.set(0)
                self.generating = False
                self._refresh_send_button_state()

                # Check if there's a pending steer (follow-up typed during generation)
                steer_text = self._pending_steer
                self._pending_steer = None
                if steer_text:
                    self._flush_pending_response_markdown()
                    self._append_chat("You: ", "user")
                    self._append_chat(f"{steer_text}\n\n")
                    self.messages.append({"role": "user", "content": steer_text})
                    self._save_conversation()
                    self._append_log_entry("User", steer_text)
                    self._schedule_token_usage_update()
                    self._start_generate()
                elif was_stopped:
                    self.status_var.set("Generation stopped.")
                else:
                    self.status_var.set("Ready.")

            self.root.after(0, _finalise)

        except Exception as e:
            traceback.print_exc(file=sys.stderr)

            def _show_error(err=e):
                self._cancel_stream_render_jobs()
                if self._active_thinking_block and self._stream_thinking_text.strip():
                    self._replace_streamed_thinking_with_markdown(self._stream_thinking_text)
                self._append_chat(f"\n[Error] {err}\n\n", "system_msg")
                self._append_log_entry("Error", str(err))
                self.status_var.set("Error occurred.")
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
                self.progress_var.set(0)
                self.generating = False
                self._refresh_send_button_state()

            self.root.after(0, _show_error)

    def _on_clear(self):
        self._cancel_stream_render_jobs()
        self._stream_response_text = ""
        self._stream_thinking_text = ""
        self._stream_response_pending_newline = False
        self._response_stream.reset()
        self._thinking_stream.reset()
        self._append_log_entry("System", "Conversation cleared.")
        self._reset_conversation()
        self._save_conversation()
        self.chat_display.configure(state=tk.NORMAL)
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.configure(state=tk.NORMAL)
        self.thinking_display.configure(state=tk.NORMAL)
        self.thinking_display.delete("1.0", tk.END)
        self.thinking_display.configure(state=tk.NORMAL)
        self._has_thinking_history = False
        self._active_thinking_block = False
        self._hide_thinking_panel()
        self._start_new_log()
        self.status_var.set("Conversation cleared.")
        self._schedule_token_usage_update()

    def _on_close(self):
        self._cancel_stream_render_jobs()
        if self._system_prompt_save_job:
            try:
                self.root.after_cancel(self._system_prompt_save_job)
            except tk.TclError:
                pass
            self._system_prompt_save_job = None
        self._save_system_prompt()
        if self._diagnostics_flush_job:
            try:
                self.root.after_cancel(self._diagnostics_flush_job)
            except tk.TclError:
                pass
            self._diagnostics_flush_job = None
            self._flush_diagnostics()
        self._capture_diagnostic(
            f"Diagnostics stopped: {datetime.now().isoformat(timespec='seconds')}\n",
            "diagnostic_meta",
        )
        if self._diagnostics_flush_job:
            try:
                self.root.after_cancel(self._diagnostics_flush_job)
            except tk.TclError:
                pass
            self._diagnostics_flush_job = None
        self._flush_diagnostics()
        self._restore_standard_streams()
        self._close_diagnostics_log()
        self.root.destroy()

