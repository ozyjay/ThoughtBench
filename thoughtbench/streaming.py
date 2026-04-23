"""Selectable streaming markdown display mixin."""

import tkinter as tk

from .markdown import MarkdownRenderer, StreamingMarkdownState, _find_stream_commit_index


class StreamingDisplayMixin:
    def _content_end(self) -> str:
        return "end-1c"

    def _cancel_stream_render_jobs(self):
        for attr in ("_response_render_job", "_thinking_render_job"):
            job = getattr(self, attr)
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    def _should_autoscroll(self, widget: tk.Text) -> bool:
        if self._selection_updates_paused(widget):
            return False

        _, bottom = widget.yview()
        return bottom >= 0.995

    def _freeze_selection_updates(self, widget: tk.Text):
        self._selection_freeze_widgets.add(str(widget))

    def _release_selection_updates(self, widget: tk.Text):
        self.root.after(350, lambda w=widget: self._clear_selection_freeze(w))

    def _clear_selection_freeze(self, widget: tk.Text):
        if self._has_active_selection(widget):
            self.root.after(350, lambda w=widget: self._clear_selection_freeze(w))
            return

        self._selection_freeze_widgets.discard(str(widget))
        self._resume_deferred_stream_render(widget)

    def _selection_updates_paused(self, widget: tk.Text) -> bool:
        return str(widget) in self._selection_freeze_widgets or self._has_active_selection(widget)

    def _has_active_selection(self, widget: tk.Text) -> bool:
        try:
            widget.index(tk.SEL_FIRST)
            widget.index(tk.SEL_LAST)
            return True
        except tk.TclError:
            return False

    def _selection_overlaps_range(self, widget: tk.Text, start: str, end: str) -> bool:
        try:
            return (
                widget.compare(tk.SEL_FIRST, "<", end)
                and widget.compare(tk.SEL_LAST, ">", start)
            )
        except tk.TclError:
            return False

    def _live_tail_updates_paused(
        self,
        widget: tk.Text,
        state: StreamingMarkdownState,
    ) -> bool:
        return (
            str(widget) in self._selection_freeze_widgets
            or self._selection_overlaps_range(widget, state.tail_mark, tk.END)
        )

    def _resume_deferred_stream_render(self, widget: tk.Text):
        if widget is self.chat_display:
            if self._response_stream.pending_final_text is not None or self._stream_response_text:
                self._schedule_streamed_response_markdown()
        elif widget is self.thinking_display:
            if self._thinking_stream.pending_final_text is not None or self._stream_thinking_text:
                self._schedule_streamed_thinking_markdown()

    def _append_to_widget(self, widget: tk.Text, text: str, tag: str | None = None):
        should_scroll = self._should_autoscroll(widget)
        widget.configure(state=tk.NORMAL)
        if tag:
            widget.insert(tk.END, text, tag)
        else:
            widget.insert(tk.END, text)
        widget.configure(state=tk.NORMAL)
        if should_scroll:
            widget.see(tk.END)

    def _append_thinking(self, text: str, tag: str | None = None):
        self._append_to_widget(self.thinking_display, text, tag)

    def _append_thinking_markdown(self, text: str):
        should_scroll = self._should_autoscroll(self.thinking_display)
        self.thinking_display.configure(state=tk.NORMAL)
        MarkdownRenderer.render(self.thinking_display, text)
        self.thinking_display.configure(state=tk.NORMAL)
        if should_scroll:
            self.thinking_display.see(tk.END)

    # ── Chat helpers ────────────────────────────────────────────────────

    def _append_chat(self, text: str, tag: str | None = None):
        self._append_to_widget(self.chat_display, text, tag)

    def _append_markdown(self, text: str):
        should_scroll = self._should_autoscroll(self.chat_display)
        self.chat_display.configure(state=tk.NORMAL)
        MarkdownRenderer.render(self.chat_display, text)
        self.chat_display.configure(state=tk.NORMAL)
        if should_scroll:
            self.chat_display.see(tk.END)
        if self._stream_response_pending_newline:
            self._stream_response_pending_newline = False
            self._append_chat("\n\n")

    def _render_streamed_response_markdown(self):
        self._response_render_job = None
        if self._response_stream.pending_final_text is not None:
            if self._selection_overlaps_range(
                self.chat_display,
                self._response_stream.start_mark,
                self._content_end(),
            ):
                self._schedule_streamed_response_markdown()
                return
            self._replace_stream_range_with_markdown(
                self.chat_display,
                self._response_stream,
                self._response_stream.pending_final_text,
                self._response_stream.pending_final_newline,
            )
            self._stream_response_pending_newline = False
            return

        if self._live_tail_updates_paused(self.chat_display, self._response_stream):
            self._schedule_streamed_response_markdown()
            return

        self._render_stream_tail(self.chat_display, self._response_stream)

    def _schedule_streamed_response_markdown(self):
        if self._response_render_job:
            self.root.after_cancel(self._response_render_job)
        self._response_render_job = self.root.after(120, self._render_streamed_response_markdown)

    def _render_streamed_thinking_markdown(self):
        self._thinking_render_job = None
        if self._thinking_stream.pending_final_text is not None:
            if self._selection_overlaps_range(
                self.thinking_display,
                self._thinking_stream.start_mark,
                self._content_end(),
            ):
                self._schedule_streamed_thinking_markdown()
                return
            self._replace_stream_range_with_markdown(
                self.thinking_display,
                self._thinking_stream,
                self._thinking_stream.pending_final_text,
                self._thinking_stream.pending_final_newline,
            )
            self._active_thinking_block = False
            self._has_thinking_history = True
            return

        if self._live_tail_updates_paused(self.thinking_display, self._thinking_stream):
            self._schedule_streamed_thinking_markdown()
            return

        self._render_stream_tail(self.thinking_display, self._thinking_stream)

    def _schedule_streamed_thinking_markdown(self):
        if self._thinking_render_job:
            self.root.after_cancel(self._thinking_render_job)
        self._thinking_render_job = self.root.after(120, self._render_streamed_thinking_markdown)

    def _replace_streamed_thinking_with_markdown(self, thinking_text: str):
        self._stream_thinking_text = thinking_text
        self._thinking_stream.text = thinking_text
        if self._selection_overlaps_range(
            self.thinking_display,
            self._thinking_stream.start_mark,
            self._content_end(),
        ):
            self._thinking_stream.pending_final_text = thinking_text
            self._thinking_stream.pending_final_newline = False
            self._schedule_streamed_thinking_markdown()
            return

        self._replace_stream_range_with_markdown(
            self.thinking_display,
            self._thinking_stream,
            thinking_text,
            append_newline=False,
        )
        self._active_thinking_block = False
        self._has_thinking_history = True

    def _render_stream_tail(self, widget: tk.Text, state: StreamingMarkdownState):
        should_scroll = self._should_autoscroll(widget)
        commit_index = _find_stream_commit_index(state.text)
        if commit_index < state.committed_len:
            commit_index = state.committed_len

        widget.configure(state=tk.NORMAL)
        try:
            widget.delete(state.tail_mark, self._content_end())
        except tk.TclError:
            widget.mark_set(state.tail_mark, self._content_end())

        if commit_index > state.committed_len:
            MarkdownRenderer.render(widget, state.text[state.committed_len:commit_index])
            state.committed_len = commit_index
            widget.mark_set(state.tail_mark, self._content_end())
            widget.mark_gravity(state.tail_mark, tk.LEFT)

        tail = state.text[state.committed_len:]
        if tail:
            # Keep the incomplete live tail raw. Markdown parsers can make
            # unstable guesses while a block is still streaming; completed
            # blocks are rendered above once a safe boundary is reached.
            widget.insert(tk.END, tail)

        widget.configure(state=tk.NORMAL)
        if should_scroll:
            widget.see(tk.END)

    def _replace_stream_range_with_markdown(
        self,
        widget: tk.Text,
        state: StreamingMarkdownState,
        text: str,
        append_newline: bool,
    ):
        should_scroll = self._should_autoscroll(widget)
        widget.configure(state=tk.NORMAL)
        try:
            widget.delete(state.start_mark, self._content_end())
        except tk.TclError:
            pass
        MarkdownRenderer.render(widget, text)
        if append_newline:
            widget.insert(tk.END, "\n\n")
        widget.mark_set(state.tail_mark, self._content_end())
        widget.mark_gravity(state.tail_mark, tk.LEFT)
        widget.configure(state=tk.NORMAL)
        state.text = text
        state.committed_len = len(text)
        state.pending_final_text = None
        state.pending_final_newline = False
        if should_scroll:
            widget.see(tk.END)

    def _stream_chunk(self, chunk: str):
        """Append a response token and refresh only the mutable markdown tail."""
        self._stream_response_text += chunk
        self._response_stream.text = self._stream_response_text
        self._schedule_live_token_usage_update()
        if self._live_tail_updates_paused(self.chat_display, self._response_stream):
            self._append_to_widget(self.chat_display, chunk)
            return

        self._schedule_streamed_response_markdown()

    def _stream_thinking_chunk(self, chunk: str):
        """Append a thinking token and refresh only the mutable markdown tail."""
        self._stream_thinking_text += chunk
        self._thinking_stream.text = self._stream_thinking_text
        if self._live_tail_updates_paused(self.thinking_display, self._thinking_stream):
            self._append_to_widget(self.thinking_display, chunk)
            return

        self._schedule_streamed_thinking_markdown()

    def _flush_pending_response_markdown(self):
        """Finish a deferred response render before appending another turn."""
        if self._response_render_job:
            try:
                self.root.after_cancel(self._response_render_job)
            except tk.TclError:
                pass
            self._response_render_job = None

        if self._response_stream.pending_final_text is not None:
            self._replace_stream_range_with_markdown(
                self.chat_display,
                self._response_stream,
                self._response_stream.pending_final_text,
                self._response_stream.pending_final_newline,
            )
            self._stream_response_pending_newline = False
        elif self._stream_response_pending_newline:
            self._stream_response_pending_newline = False
            self._append_chat("\n\n")

    def _replace_streamed_with_markdown(self, response_text):
        """Delete the raw streamed text and re-render with markdown formatting."""
        self._stream_response_text = response_text
        self._response_stream.text = response_text
        if self._selection_overlaps_range(
            self.chat_display,
            self._response_stream.start_mark,
            self._content_end(),
        ):
            self._response_stream.pending_final_text = response_text
            self._response_stream.pending_final_newline = True
            self._schedule_streamed_response_markdown()
            self._stream_response_pending_newline = True
            return

        self._replace_stream_range_with_markdown(
            self.chat_display,
            self._response_stream,
            response_text,
            append_newline=True,
        )
        self._stream_response_pending_newline = False
