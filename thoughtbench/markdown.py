"""Markdown rendering and streaming markdown state."""

import re
import tkinter as tk

from markdown_it import MarkdownIt


class MarkdownRenderer:
    """Inserts markdown-formatted text into a tk.Text widget using tags."""

    _md = MarkdownIt("commonmark")

    @classmethod
    def render(cls, widget: tk.Text, text: str):
        """Parse *text* as markdown and insert styled content into *widget*."""
        tokens = cls._md.parse(text)
        cls._walk(widget, tokens)

    @classmethod
    def _walk(cls, widget: tk.Text, tokens):
        tag_stack: list[str] = []
        list_stack: list[dict[str, int | bool]] = []
        in_list_item = False

        for tok in tokens:
            # --- block openers / closers ---
            if tok.type == "heading_open":
                level = int(tok.tag[1])  # h1..h6
                tag_stack.append(f"h{level}")
            elif tok.type == "heading_close":
                widget.insert(tk.END, "\n\n")
                if tag_stack:
                    tag_stack.pop()
            elif tok.type == "paragraph_open":
                pass
            elif tok.type == "paragraph_close":
                # Inside list items, use single newline; otherwise double
                if in_list_item:
                    widget.insert(tk.END, "\n")
                else:
                    widget.insert(tk.END, "\n\n")
            elif tok.type == "blockquote_open":
                tag_stack.append("blockquote")
            elif tok.type == "blockquote_close":
                if tag_stack and tag_stack[-1] == "blockquote":
                    tag_stack.pop()
            elif tok.type == "bullet_list_open":
                list_stack.append({"ordered": False, "counter": 0})
            elif tok.type == "bullet_list_close":
                if list_stack:
                    list_stack.pop()
                if not list_stack:
                    widget.insert(tk.END, "\n")
            elif tok.type == "ordered_list_open":
                start = 1
                if tok.attrs:
                    for key, value in tok.attrs.items():
                        if key == "start":
                            try:
                                start = int(value)
                            except (TypeError, ValueError):
                                start = 1
                            break
                list_stack.append({"ordered": True, "counter": start})
            elif tok.type == "ordered_list_close":
                if list_stack:
                    list_stack.pop()
                if not list_stack:
                    widget.insert(tk.END, "\n")
            elif tok.type == "list_item_open":
                in_list_item = True
                depth = max(0, len(list_stack) - 1)
                indent = "  " * depth
                prefix = "• "
                if list_stack and bool(list_stack[-1]["ordered"]):
                    counter = int(list_stack[-1]["counter"])
                    prefix = f"{counter}. "
                    list_stack[-1]["counter"] = counter + 1
                widget.insert(
                    tk.END,
                    f"{indent}{prefix}",
                    tuple(tag_stack) if tag_stack else (),
                )
            elif tok.type == "list_item_close":
                in_list_item = False
            elif tok.type == "fence":
                # Show language label if present
                info = (tok.info or "").strip()
                if info:
                    widget.insert(tk.END, f"[{info}]\n", ("code_block",))
                widget.insert(tk.END, tok.content, ("code_block",))
                widget.insert(tk.END, "\n")
            elif tok.type == "code_block":
                widget.insert(tk.END, tok.content, ("code_block",))
                widget.insert(tk.END, "\n")
            elif tok.type == "hr":
                widget.insert(tk.END, "─" * 40 + "\n\n")
            elif tok.type == "inline":
                cls._render_inline(widget, tok.children or [], tag_stack)

    @classmethod
    def _render_inline(cls, widget: tk.Text, children, parent_tags: list[str]):
        tag_stack = list(parent_tags)
        for tok in children:
            if tok.type == "text":
                widget.insert(tk.END, tok.content, tuple(tag_stack) if tag_stack else ())
            elif tok.type == "softbreak":
                widget.insert(tk.END, "\n", tuple(tag_stack) if tag_stack else ())
            elif tok.type == "hardbreak":
                widget.insert(tk.END, "\n", tuple(tag_stack) if tag_stack else ())
            elif tok.type == "strong_open":
                tag_stack.append("bold")
            elif tok.type == "strong_close":
                if "bold" in tag_stack:
                    tag_stack.remove("bold")
            elif tok.type == "em_open":
                tag_stack.append("italic")
            elif tok.type == "em_close":
                if "italic" in tag_stack:
                    tag_stack.remove("italic")
            elif tok.type == "code_inline":
                widget.insert(tk.END, tok.content, ("code_inline",))
            elif tok.type == "html_inline":
                widget.insert(tk.END, tok.content, tuple(tag_stack) if tag_stack else ())


class StreamingMarkdownState:
    """Tracks the mutable tail of a streaming markdown render."""

    def __init__(self, start_mark: str, tail_mark: str):
        self.start_mark = start_mark
        self.tail_mark = tail_mark
        self.text = ""
        self.committed_len = 0
        self.pending_final_text: str | None = None
        self.pending_final_newline = False

    def reset(self):
        self.text = ""
        self.committed_len = 0
        self.pending_final_text = None
        self.pending_final_newline = False


def _find_stream_commit_index(text: str) -> int:
    """Return a safe character offset through completed markdown blocks."""
    commit = 0
    offset = 0
    in_fence = False
    fence_marker = ""

    for line in text.splitlines(keepends=True):
        line_end = offset + len(line)
        has_newline = line.endswith(("\n", "\r"))
        stripped = line.strip()
        fence_match = re.match(r"^\s{0,3}(```+|~~~+)", line)

        if fence_match:
            marker = fence_match.group(1)
            marker_char = marker[0]
            if in_fence:
                if marker_char == fence_marker and has_newline:
                    in_fence = False
                    fence_marker = ""
                    commit = line_end
            else:
                in_fence = True
                fence_marker = marker_char
            offset = line_end
            continue

        if not in_fence and has_newline:
            is_heading = bool(re.match(r"^\s{0,3}#{1,6}\s+", line))
            is_rule = bool(re.match(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$", line))
            if not stripped or is_heading or is_rule:
                commit = line_end

        offset = line_end

    return commit


