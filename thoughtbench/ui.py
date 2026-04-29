"""Tkinter UI for the Thoughtbench desktop chat application."""

import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import scrolledtext, ttk

import sv_ttk
from huggingface_hub import try_to_load_from_cache

from .behaviour import BehaviourMixin
from .config import (
    APP_NAME,
    MODEL_CATALOG,
    THEMES,
    get_model_option,
    valid_model_id_or_default,
)
from .diagnostics_mixin import DiagnosticsMixin
from .knowledge import DEFAULT_KNOWLEDGE_SETTINGS
from .persistence import PersistenceMixin
from .resources import _resource_path
from .runtime import RuntimeMixin
from .stats import StatsMonitor
from .markdown import StreamingMarkdownState
from .streaming import StreamingDisplayMixin


EXPECTED_SECTION_IDS = (
    "chat",
    "behaviour",
    "profiles",
    "knowledge",
    "diagnostics",
    "settings",
)
DEFAULT_SECTION_ID = "chat"


@dataclass(frozen=True)
class SidebarSection:
    section_id: str
    label: str
    builder_name: str


def build_section_registry() -> tuple[SidebarSection, ...]:
    return (
        SidebarSection("chat", "Chat", "_build_chat_section"),
        SidebarSection("behaviour", "Behaviour", "_build_behaviour_section"),
        SidebarSection("profiles", "Profiles", "_build_profiles_section"),
        SidebarSection("knowledge", "Knowledge", "_build_knowledge_section"),
        SidebarSection("diagnostics", "Diagnostics", "_build_diagnostics_section"),
        SidebarSection("settings", "Settings", "_build_settings_section"),
    )


class CircularProgressIndicator:
    """Small status-bar progress indicator with a Progressbar-like interface."""

    def __init__(
        self,
        parent: tk.Widget,
        variable: tk.DoubleVar,
        maximum: float = 100,
        size: int = 22,
    ):
        self.variable = variable
        self.maximum = maximum
        self.size = size
        self.mode = "determinate"
        self._running = False
        self._angle = 90
        self._job: str | None = None
        self._background = "#20242d"
        self._track = "#2b313d"
        self._accent = "#38bdf8"
        self.canvas = tk.Canvas(
            parent,
            width=size,
            height=size,
            highlightthickness=0,
            borderwidth=0,
            relief=tk.FLAT,
        )
        self.variable.trace_add("write", lambda *_args: self._draw())
        self._draw()

    def pack(self, *args, **kwargs):
        self.canvas.pack(*args, **kwargs)

    def pack_forget(self):
        self.canvas.pack_forget()

    def configure(self, **kwargs):
        mode = kwargs.pop("mode", None)
        if mode is not None:
            self.mode = mode
        if kwargs:
            self.canvas.configure(**kwargs)
        self._draw()

    def start(self, interval: int = 50):
        self._running = True
        self._tick(max(15, int(interval)))

    def stop(self):
        self._running = False
        if self._job is not None:
            try:
                self.canvas.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        self._draw()

    def set_palette(self, background: str, track: str, accent: str):
        self._background = background
        self._track = track
        self._accent = accent
        self.canvas.configure(bg=background)
        self._draw()

    def _tick(self, interval: int):
        if not self._running:
            return
        self._angle = (self._angle - 24) % 360
        self._draw()
        self._job = self.canvas.after(interval, lambda: self._tick(interval))

    def _draw(self):
        self.canvas.delete("all")
        pad = 4
        bounds = (pad, pad, self.size - pad, self.size - pad)
        self.canvas.create_oval(bounds, outline=self._track, width=2)

        if self.mode == "indeterminate" and self._running:
            self.canvas.create_arc(
                bounds,
                start=self._angle,
                extent=105,
                style=tk.ARC,
                outline=self._accent,
                width=3,
            )
            return

        try:
            value = float(self.variable.get())
        except (tk.TclError, ValueError):
            value = 0
        pct = 0 if self.maximum <= 0 else max(0, min(1, value / self.maximum))
        if pct > 0:
            self.canvas.create_arc(
                bounds,
                start=90,
                extent=-359.9 * pct,
                style=tk.ARC,
                outline=self._accent,
                width=3,
            )


class ThoughtbenchApp(
    PersistenceMixin,
    DiagnosticsMixin,
    StreamingDisplayMixin,
    BehaviourMixin,
    RuntimeMixin,
):
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1080x780")
        self.root.minsize(780, 560)
        self._window_icon: tk.PhotoImage | None = None

        self.processor = None
        self.model = None
        self.selected_model_id = valid_model_id_or_default(None)
        self.active_model_option = None
        self.selected_model_var = tk.StringVar()
        self._model_label_to_id: dict[str, str] = {}
        self.messages: list[dict] = []
        self.generating = False
        self.updating_behaviour = False
        self._pending_send = False
        self._stop_event = threading.Event()
        self._pending_steer: str | None = None
        self.stats = None
        self._load_start: float = 0
        self._stream_response_text = ""
        self._stream_thinking_text = ""
        self._stream_response_pending_newline = False
        self._response_stream = StreamingMarkdownState(
            "stream_start",
            "response_live_tail_start",
        )
        self._thinking_stream = StreamingMarkdownState(
            "thinking_stream_start",
            "thinking_live_tail_start",
        )
        self._selection_freeze_widgets: set[str] = set()
        self._response_render_job: str | None = None
        self._thinking_render_job: str | None = None
        self._has_thinking_history = False
        self._active_thinking_block = False
        self.log_dir: Path | None = None
        self.log_path: Path | None = None
        self.knowledge_index = None
        self.knowledge_index_stale = False
        self.knowledge_settings = DEFAULT_KNOWLEDGE_SETTINGS
        self.last_retrieved_knowledge = []
        self._retrieved_knowledge_visible = False
        self._pending_generation_messages: list[dict] | None = None
        self._system_prompt_save_job: str | None = None
        self._system_prompt_history: list[dict] = []
        self._system_prompt_history_labels: list[str] = []
        self._system_prompt_min_lines = 2
        self._system_prompt_max_lines = 8
        self.system_prompt_lines = tk.IntVar(value=self._system_prompt_min_lines)
        self.system_prompt_history_var = tk.StringVar(value="Prompt history")
        self.profile_var = tk.StringVar(value="No profiles")
        self._profile_label_to_dir: dict[str, Path] = {}
        self.diagnostics_log_path: Path | None = None
        self._diagnostics_log_handle = None
        self._diagnostics_visible = False
        self._behaviour_visible = False
        self._loading_screen_visible = False
        self._diagnostics_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._diagnostics_flush_job: str | None = None
        self._stdout_original = sys.stdout
        self._stderr_original = sys.stderr
        self._diagnostics_redirected = False
        self._suppress_stream_diagnostics = False
        self.token_usage_var = tk.StringVar(value="Tokens: loading")
        self._token_prompt_tokens = 0
        self._token_reserved_tokens = 0
        self._token_context_limit: int | None = None
        self._token_usage_pct = 0.0
        self._token_usage_state = "loading"
        self._token_prompt_over_limit = False
        self._token_update_job: str | None = None
        self._token_update_revision = 0
        self._slash_commands = [
            ("/behaviour", "rewrite Assistant Behaviour from advice"),
            ("/think", "toggle thinking mode"),
            ("/reset", "clear conversation history"),
        ]
        self._slash_popup_visible = False
        self._generation_sliders: list[ttk.Scale] = []
        self._generation_controls: list[dict] = []
        self._suppress_generation_status = False

        # Font settings
        self._available_fonts: list[str] = []
        self.font_family = tk.StringVar(value="Cascadia Code")
        self.font_size = tk.IntVar(value=11)

        # Theme
        self.is_dark = True
        sv_ttk.set_theme("dark")

        self._apply_window_icon()
        self._build_ui()
        self.selected_model_id = self._read_selected_model_id()
        self._apply_theme()
        self._apply_fonts()
        self.system_prompt.bind("<<Modified>>", self._on_system_prompt_modified)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._finish_startup_async)

    def _finish_startup_async(self):
        self.status_var.set("Choose a model to load.")
        self.root.after(0, self._finish_startup)

    def _finish_startup(self):
        self._prompt_for_startup_model()

    def _finish_startup_after_model_choice(self):
        self.status_var.set("Preparing workspace...")
        self._setup_logging()
        self._load_saved_conversation()
        self._setup_diagnostics_capture()
        self.stats = StatsMonitor()
        self._start_stats_loop()
        self._load_model_async()

    # ── UI construction ─────────────────────────────────────────────────

    def _apply_window_icon(self):
        png_path = _resource_path("assets", "app-icon.png")
        ico_path = _resource_path("assets", "app-icon.ico")

        try:
            if ico_path.exists():
                self.root.iconbitmap(default=str(ico_path))
        except tk.TclError:
            pass

        try:
            if png_path.exists():
                self._window_icon = tk.PhotoImage(file=str(png_path))
                self.root.iconphoto(True, self._window_icon)
                return
        except tk.TclError:
            self._window_icon = None

        try:
            if ico_path.exists():
                self.root.iconbitmap(str(ico_path))
        except tk.TclError:
            pass

    def _build_ui(self):
        self.status_var = tk.StringVar(value="Loading model...")
        self.progress_var = tk.DoubleVar(value=0)
        self.stats_var = tk.StringVar(value="")
        self.context_profile_var = tk.StringVar(value="Profile: No profiles")
        self.context_model_var = tk.StringVar(value="Model: loading")
        self.context_thinking_var = tk.StringVar(value="Thinking: off")
        self.context_knowledge_var = tk.StringVar(value="Knowledge: unknown")

        self.section_registry = build_section_registry()
        self.sidebar_buttons: dict[str, ttk.Button] = {}
        self.secondary_frames: dict[str, ttk.Frame] = {}
        self.active_section_id = DEFAULT_SECTION_ID

        # Font options are built before the Settings section creates controls.
        all_system = {f for f in tkfont.families() if not f.startswith("@")}
        coding_fonts = [
            "Cascadia Code", "Cascadia Mono",
            "Consolas", "Courier New",
            "Fira Code", "Fira Mono",
            "Hack", "Inconsolata",
            "JetBrains Mono", "Menlo", "Monaco",
            "Source Code Pro", "Ubuntu Mono",
            "DejaVu Sans Mono", "Droid Sans Mono",
            "IBM Plex Mono", "Roboto Mono",
            "SF Mono", "Victor Mono",
            "Anonymous Pro", "Input Mono",
            "Iosevka", "Noto Sans Mono",
            "PT Mono", "Space Mono",
            "0xProto", "Agave", "Andale Mono",
            "Aptos Mono", "B612 Mono",
            "Berkeley Mono", "Bitstream Vera Sans Mono",
            "CommitMono", "Comic Code",
            "Cousine", "Dank Mono",
            "DM Mono", "Envy Code R",
            "Fragment Mono", "Geist Mono",
            "Go Mono", "Hasklig",
            "Intel One Mono", "JuliaMono",
            "Lekton", "Liberation Mono",
            "Maple Mono", "Martian Mono",
            "MesloLGS NF", "Monaspace Argon",
            "Monaspace Krypton", "Monaspace Neon",
            "Monaspace Radon", "Monaspace Xenon",
            "Operator Mono", "Overpass Mono",
            "PragmataPro", "ProFont",
            "Recursive Mono", "Red Hat Mono",
            "Sometype Mono", "Terminus",
            "Ubuntu Sans Mono", "Zed Mono",
        ]
        available = sorted(
            [f for f in coding_fonts if f in all_system], key=str.lower
        )
        if not available:
            # Fallback: include any mono/courier fonts from the system
            available = sorted(
                [f for f in all_system if any(k in f.lower() for k in ("mono", "courier", "consol"))],
                key=str.lower,
            ) or ["Courier New"]
        self._available_fonts = available
        # Resolve default font
        for preferred in ("Cascadia Code", "Cascadia Mono", "Consolas", "Courier New"):
            if preferred in available:
                self.font_family.set(preferred)
                break

        status_frame = ttk.Frame(self.root, padding=(12, 6), style="Status.TFrame")
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Label(
            status_frame,
            textvariable=self.status_var,
            anchor=tk.W,
            style="Status.TLabel",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.progress_bar = CircularProgressIndicator(
            status_frame,
            variable=self.progress_var,
            maximum=100,
            size=22,
        )
        self.progress_bar.pack(side=tk.LEFT, padx=(0, 10))
        self._status_progress_visible = True

        self.elapsed_var = tk.StringVar(value="")
        self.elapsed_label = ttk.Label(
            status_frame,
            textvariable=self.elapsed_var,
            anchor=tk.E,
            style="Status.TLabel",
        )
        self.elapsed_label.pack(side=tk.RIGHT)

        self.stats_bar = ttk.Frame(
            self.root,
            padding=(12, 3),
            style="Status.TFrame",
        )
        self.stats_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.stats_label = ttk.Label(
            self.stats_bar,
            textvariable=self.stats_var,
            anchor=tk.W,
            style="Stats.TLabel",
        )
        self.stats_label.pack(side=tk.LEFT)
        ttk.Label(
            self.stats_bar,
            text="  |  ",
            style="Stats.TLabel",
        ).pack(side=tk.LEFT)
        self.token_stats_label = ttk.Label(
            self.stats_bar,
            textvariable=self.token_usage_var,
            anchor=tk.W,
            style="Stats.TLabel",
        )
        self.token_stats_label.pack(side=tk.LEFT)

        app_body = ttk.Frame(self.root, style="App.TFrame")
        app_body.pack(fill=tk.BOTH, expand=True)

        self.sidebar_frame = ttk.Frame(app_body, padding=(10, 12), style="Sidebar.TFrame")
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        ttk.Label(
            self.sidebar_frame,
            text=APP_NAME,
            style="SidebarTitle.TLabel",
        ).pack(anchor=tk.W, pady=(0, 12))
        for section in self.section_registry:
            button = ttk.Button(
                self.sidebar_frame,
                text=section.label,
                command=lambda section_id=section.section_id: self._select_sidebar_section(section_id),
            )
            button.pack(fill=tk.X, pady=(0, 6))
            self.sidebar_buttons[section.section_id] = button

        self.workspace_pane = ttk.PanedWindow(app_body, orient=tk.HORIZONTAL)
        self.workspace_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.main_workspace = ttk.Frame(self.workspace_pane, padding=(12, 10), style="App.TFrame")
        self.secondary_workspace = ttk.Frame(self.workspace_pane, padding=(0, 10, 12, 10), style="App.TFrame")
        self.workspace_pane.add(self.main_workspace, weight=4)
        self.workspace_pane.add(self.secondary_workspace, weight=1)

        self._build_context_strip()
        self._build_chat_workspace()
        self._build_secondary_sections()
        self._select_sidebar_section(DEFAULT_SECTION_ID)

    def _build_context_strip(self):
        self.context_strip = ttk.Frame(self.main_workspace, padding=(10, 7), style="Panel.TFrame")
        self.context_strip.pack(fill=tk.X, pady=(0, 8))

        for variable in (
            self.context_model_var,
            self.context_profile_var,
            self.context_thinking_var,
            self.context_knowledge_var,
        ):
            ttk.Label(
                self.context_strip,
                textvariable=variable,
                style="Stats.TLabel",
            ).pack(side=tk.LEFT, padx=(0, 14))

        ttk.Button(
            self.context_strip,
            text="Copy Latest",
            command=self._copy_latest_response,
        ).pack(side=tk.RIGHT)

    def _build_chat_workspace(self):
        self.chat_pane = ttk.PanedWindow(self.main_workspace, orient=tk.VERTICAL)
        self.chat_pane.pack(fill=tk.BOTH, expand=True)

        self.thinking_frame = ttk.Frame(self.main_workspace, padding=(12, 10), style="Panel.TFrame")
        ttk.Label(
            self.thinking_frame,
            text="Thinking",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        self.thinking_display = scrolledtext.ScrolledText(
            self.thinking_frame, wrap=tk.WORD, state=tk.NORMAL, relief=tk.FLAT,
            borderwidth=0, padx=10, pady=10, height=8,
        )
        self.thinking_display.pack(fill=tk.BOTH, expand=True)

        self.main_chat_frame = ttk.Frame(self.main_workspace, padding=(12, 10), style="Panel.TFrame")
        ttk.Label(
            self.main_chat_frame,
            text="Conversation",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        self.chat_display = scrolledtext.ScrolledText(
            self.main_chat_frame, wrap=tk.WORD, state=tk.NORMAL, relief=tk.FLAT,
            borderwidth=0, padx=10, pady=10,
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)

        input_frame = ttk.Frame(self.main_workspace, padding=(0, 8, 0, 0), style="Input.TFrame")
        input_frame.pack(fill=tk.X)

        self.user_input = tk.Text(
            input_frame,
            height=3,
            wrap=tk.WORD,
            relief=tk.FLAT,
            borderwidth=0,
            padx=10,
            pady=8,
        )
        self.user_input.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        self.user_input.bind("<Return>", self._on_enter)
        self.user_input.bind("<Shift-Return>", lambda e: None)
        self.user_input.bind("<Escape>", self._hide_slash_command_popup)
        self.user_input.bind("<Tab>", self._complete_selected_slash_command)
        self.user_input.bind("<Down>", self._slash_command_down)
        self.user_input.bind("<Up>", self._slash_command_up)
        self.user_input.bind("<KeyRelease>", self._on_user_input_changed)
        self.user_input.bind("<<Paste>>", self._on_user_input_changed)

        self.slash_popup = tk.Listbox(
            input_frame,
            height=3,
            activestyle="none",
            exportselection=False,
            relief=tk.FLAT,
            borderwidth=0,
        )
        self.slash_popup.bind("<ButtonRelease-1>", self._complete_selected_slash_command)
        self.slash_popup.bind("<Return>", self._complete_selected_slash_command)
        self._slash_popup_items: list[tuple[str, str]] = []

        btn_frame = ttk.Frame(input_frame, style="Input.TFrame")
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.think_var = tk.BooleanVar(value=False)
        self.think_check = ttk.Checkbutton(
            btn_frame,
            text="Thinking",
            variable=self.think_var,
            command=self._on_thinking_mode_changed,
        )
        self.think_check.pack(fill=tk.X, pady=(0, 5))

        self.send_btn = ttk.Button(btn_frame, text="Send", command=self._on_send)
        self.send_btn.pack(fill=tk.X, pady=(0, 5))
        self.clear_btn = ttk.Button(btn_frame, text="Clear", command=self._on_clear)
        self.clear_btn.pack(fill=tk.X)

        self.loading_frame = ttk.Frame(self.main_workspace, padding=32, style="Panel.TFrame")
        self.loading_frame.columnconfigure(0, weight=1)
        self.loading_frame.rowconfigure(0, weight=1)

        loading_content = ttk.Frame(self.loading_frame, padding=24, style="Panel.TFrame")
        loading_content.grid(row=0, column=0)

        ttk.Label(
            loading_content,
            text=APP_NAME,
            font=(self.font_family.get(), 20, "bold"),
            anchor=tk.CENTER,
        ).pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            loading_content,
            text="Preparing the local model",
            font=(self.font_family.get(), 12),
            anchor=tk.CENTER,
        ).pack(fill=tk.X, pady=(0, 18))
        self.loading_status_label = ttk.Label(
            loading_content,
            textvariable=self.status_var,
            anchor=tk.CENTER,
            wraplength=520,
        )
        self.loading_status_label.pack(fill=tk.X, pady=(0, 10))
        self.loading_progress = ttk.Progressbar(
            loading_content,
            variable=self.progress_var,
            maximum=100,
            length=520,
        )
        self.loading_progress.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            loading_content,
            text=(
                "First launch may take a while if the model needs to download. "
                "Later launches still need to load weights into GPU memory."
            ),
            anchor=tk.CENTER,
            justify=tk.CENTER,
            wraplength=520,
        ).pack(fill=tk.X)

        self._make_readonly_display(self.thinking_display)
        self._make_readonly_display(self.chat_display)
        self.chat_pane.add(self.loading_frame, weight=3)
        self._loading_screen_visible = True
        self._thinking_visible = False

    def _build_secondary_sections(self):
        self.secondary_header_var = tk.StringVar(value="")
        header = ttk.Frame(self.secondary_workspace, padding=(12, 0, 0, 8), style="App.TFrame")
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            textvariable=self.secondary_header_var,
            style="Section.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Button(
            header,
            text="Hide",
            command=self._hide_secondary_workspace,
        ).pack(side=tk.RIGHT)

        self.secondary_stack = ttk.Frame(self.secondary_workspace, style="App.TFrame")
        self.secondary_stack.pack(fill=tk.BOTH, expand=True)
        for section in self.section_registry:
            builder = getattr(self, section.builder_name)
            frame = builder(self.secondary_stack)
            self.secondary_frames[section.section_id] = frame

    def _build_chat_section(self, parent):
        frame = ttk.Frame(parent, padding=(12, 10), style="Panel.TFrame")
        ttk.Label(frame, text="Current Context", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
        for variable in (
            self.context_model_var,
            self.context_profile_var,
            self.context_thinking_var,
            self.context_knowledge_var,
        ):
            ttk.Label(frame, textvariable=variable, style="Stats.TLabel").pack(anchor=tk.W, pady=(0, 6))
        ttk.Button(frame, text="Copy Latest Response", command=self._copy_latest_response).pack(fill=tk.X, pady=(8, 0))
        ttk.Button(frame, text="Clear Conversation", command=self._on_clear).pack(fill=tk.X, pady=(6, 0))
        return frame

    def _build_behaviour_section(self, parent):
        frame = ttk.Frame(parent, padding=(12, 10), style="Panel.TFrame")
        ttk.Label(frame, text="Assistant Behaviour", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
        history_row = ttk.Frame(frame, style="Panel.TFrame")
        history_row.pack(fill=tk.X, pady=(0, 8))
        self.system_prompt_history_combo = ttk.Combobox(
            history_row,
            textvariable=self.system_prompt_history_var,
            values=[],
            state=tk.DISABLED,
        )
        self.system_prompt_history_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.system_prompt_history_combo.bind(
            "<Return>",
            lambda _event: self._restore_selected_system_prompt(),
        )
        self.restore_system_prompt_btn = ttk.Button(
            history_row,
            text="Restore",
            command=self._restore_selected_system_prompt,
            state=tk.DISABLED,
        )
        self.restore_system_prompt_btn.pack(side=tk.RIGHT)

        self.system_prompt = tk.Text(
            frame,
            height=self.system_prompt_lines.get(),
            wrap=tk.WORD,
            undo=True,
            autoseparators=True,
            maxundo=200,
            relief=tk.FLAT,
            borderwidth=0,
            padx=10,
            pady=8,
        )
        self.system_prompt.insert("1.0", "You are a helpful assistant.")
        self.system_prompt.edit_reset()
        self.system_prompt.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self._bind_system_prompt_editing()
        self._apply_system_prompt_height()

        self.behaviour_btn = ttk.Button(
            frame, text="Rewrite Behaviour From Input", command=self._on_update_behaviour
        )
        self.behaviour_btn.pack(fill=tk.X)
        return frame

    def _build_profiles_section(self, parent):
        frame = ttk.Frame(parent, padding=(12, 10), style="Panel.TFrame")
        ttk.Label(frame, text="Profiles", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(frame, text="Active profile", style="Toolbar.TLabel").pack(anchor=tk.W)
        self.profile_combo = ttk.Combobox(
            frame,
            textvariable=self.profile_var,
            values=[],
            state=tk.DISABLED,
        )
        self.profile_combo.pack(fill=tk.X, pady=(4, 10))
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        ttk.Button(frame, text="New Profile", command=self._on_new_profile).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(frame, text="Add Profile Folder", command=self._on_add_existing_profile).pack(fill=tk.X)
        return frame

    def _build_knowledge_section(self, parent):
        frame = ttk.Frame(parent, padding=(12, 10), style="Panel.TFrame")
        ttk.Label(frame, text="Knowledge", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
        self.knowledge_status_var = tk.StringVar(value="Knowledge index status will appear here.")
        ttk.Label(
            frame,
            textvariable=self.knowledge_status_var,
            style="Stats.TLabel",
            wraplength=300,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(frame, text="Open Knowledge Folder", command=self._on_open_knowledge_folder).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(frame, text="Rebuild Knowledge Index", command=self._on_rebuild_knowledge_index).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(frame, text="Knowledge Settings...", command=self._on_knowledge_settings).pack(fill=tk.X, pady=(0, 12))

        self.retrieved_knowledge_frame = ttk.Frame(frame, padding=(8, 6), style="Panel.TFrame")
        self.retrieved_knowledge_frame.pack(fill=tk.BOTH, expand=True)
        retrieved_header = ttk.Frame(self.retrieved_knowledge_frame, style="Panel.TFrame")
        retrieved_header.pack(fill=tk.X)
        self.retrieved_knowledge_toggle = ttk.Button(
            retrieved_header,
            text="Retrieved Knowledge",
            command=self._toggle_retrieved_knowledge_panel,
        )
        self.retrieved_knowledge_toggle.pack(side=tk.LEFT)
        self.retrieved_knowledge_summary_var = tk.StringVar(value="No snippets")
        ttk.Label(
            retrieved_header,
            textvariable=self.retrieved_knowledge_summary_var,
            style="Toolbar.TLabel",
        ).pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)
        self.retrieved_knowledge_display = scrolledtext.ScrolledText(
            self.retrieved_knowledge_frame,
            wrap=tk.WORD,
            state=tk.NORMAL,
            relief=tk.FLAT,
            borderwidth=0,
            padx=8,
            pady=6,
            height=8,
        )
        self.retrieved_knowledge_display.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self._retrieved_knowledge_visible = True
        self._make_readonly_display(self.retrieved_knowledge_display)
        return frame

    def _build_diagnostics_section(self, parent):
        self.diagnostics_frame = ttk.Frame(parent, padding=(12, 10), style="Panel.TFrame")
        ttk.Label(
            self.diagnostics_frame,
            text="Diagnostics",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 6))
        self.diagnostics_display = scrolledtext.ScrolledText(
            self.diagnostics_frame, wrap=tk.WORD, state=tk.NORMAL, relief=tk.FLAT,
            borderwidth=0, padx=10, pady=10, height=8,
        )
        self.diagnostics_display.pack(fill=tk.BOTH, expand=True)
        self._make_readonly_display(self.diagnostics_display)
        return self.diagnostics_frame

    def _build_settings_section(self, parent):
        frame = ttk.Frame(parent, padding=(12, 10), style="Panel.TFrame")
        ttk.Label(frame, text="Settings", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
        self.theme_btn = ttk.Button(frame, text="Light Theme", command=self._toggle_theme)
        self.theme_btn.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(frame, text="Font", style="Toolbar.TLabel").pack(anchor=tk.W)
        font_combo = ttk.Combobox(
            frame,
            textvariable=self.font_family,
            values=self._available_fonts,
            state="readonly",
        )
        font_combo.pack(fill=tk.X, pady=(4, 10))
        font_combo.bind("<<ComboboxSelected>>", lambda _: self._apply_fonts())

        ttk.Label(frame, text="Size", style="Toolbar.TLabel").pack(anchor=tk.W)
        size_spin = ttk.Spinbox(
            frame,
            from_=8,
            to=24,
            increment=1,
            textvariable=self.font_size,
            width=5,
            command=self._apply_fonts,
        )
        size_spin.pack(anchor=tk.W, pady=(4, 14))

        self.params_frame = ttk.Frame(frame, padding=(0, 0), style="Params.TFrame")
        self.params_frame.pack(fill=tk.X)
        self.generation_defaults = {
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 64,
            "max_tokens": 1024,
        }
        self.temp_var = tk.DoubleVar(value=self.generation_defaults["temperature"])
        self.top_p_var = tk.DoubleVar(value=self.generation_defaults["top_p"])
        self.top_k_var = tk.IntVar(value=self.generation_defaults["top_k"])
        self.max_tokens_var = tk.IntVar(value=self.generation_defaults["max_tokens"])
        self._make_generation_slider(
            self.params_frame,
            label="Creativity",
            variable=self.temp_var,
            default=self.generation_defaults["temperature"],
            from_=0.1,
            to=2.0,
            resolution=0.1,
            formatter=lambda value: f"{value:.1f} - {self._creativity_label(value)}",
        )
        self._make_generation_slider(
            self.params_frame,
            label="Variety",
            variable=self.top_p_var,
            default=self.generation_defaults["top_p"],
            from_=0.1,
            to=1.0,
            resolution=0.05,
            formatter=lambda value: f"{value:.2f} - {self._variety_label(value)}",
        )
        self._make_generation_slider(
            self.params_frame,
            label="Choice pool",
            variable=self.top_k_var,
            default=self.generation_defaults["top_k"],
            from_=1,
            to=200,
            resolution=1,
            formatter=lambda value: f"{int(value)} - {self._choice_pool_label(value)}",
            integer=True,
        )
        self._make_generation_slider(
            self.params_frame,
            label="Reply length",
            variable=self.max_tokens_var,
            default=self.generation_defaults["max_tokens"],
            from_=64,
            to=8192,
            resolution=64,
            formatter=lambda value: f"{int(value)} - {self._reply_length_label(value)}",
            integer=True,
            expand=True,
        )
        self.max_tokens_var.trace_add("write", lambda *_args: self._schedule_token_usage_update())
        ttk.Button(frame, text="Reset Generation Settings", command=self._reset_generation_settings).pack(fill=tk.X, pady=(12, 0))
        return frame

    def _select_sidebar_section(self, section_id: str):
        if section_id not in self.secondary_frames:
            section_id = DEFAULT_SECTION_ID

        for frame in self.secondary_frames.values():
            frame.pack_forget()
        self.secondary_frames[section_id].pack(fill=tk.BOTH, expand=True)
        self.active_section_id = section_id

        section = next(
            (item for item in self.section_registry if item.section_id == section_id),
            self.section_registry[0],
        )
        self.secondary_header_var.set(section.label)
        for current_id, button in self.sidebar_buttons.items():
            button.state(["pressed"] if current_id == section_id else ["!pressed"])

        if not self._secondary_workspace_visible():
            self.workspace_pane.add(self.secondary_workspace, weight=1)

        if section_id == "diagnostics":
            self._diagnostics_visible = True
            self.diagnostics_display.see(tk.END)

    def _hide_secondary_workspace(self):
        try:
            self.workspace_pane.remove(self.secondary_workspace)
        except tk.TclError:
            pass

    def _secondary_workspace_visible(self) -> bool:
        return str(self.secondary_workspace) in [str(pane) for pane in self.workspace_pane.panes()]

    def _refresh_context_strip(self):
        if not hasattr(self, "context_model_var"):
            return
        self.context_model_var.set(f"Model: {self._assistant_display_name()}")
        self.context_profile_var.set(f"Profile: {self.profile_var.get()}")
        self.context_thinking_var.set(f"Thinking: {'on' if self.think_var.get() else 'off'}")
        self.context_knowledge_var.set(self._knowledge_status_text())
        if hasattr(self, "knowledge_status_var"):
            self.knowledge_status_var.set(self._knowledge_status_text())

    def _make_readonly_display(self, widget: tk.Text):
        widget.configure(cursor="xterm", takefocus=True)
        widget.bind("<Key>", self._block_readonly_edit)
        widget.bind("<<Paste>>", lambda _event: "break")
        widget.bind("<<Cut>>", lambda _event: "break")
        widget.bind("<Control-a>", lambda _event, w=widget: self._select_all_text(w))
        widget.bind("<Control-A>", lambda _event, w=widget: self._select_all_text(w))
        widget.bind("<ButtonPress-1>", lambda _event, w=widget: self._freeze_selection_updates(w), add="+")
        widget.bind("<B1-Motion>", lambda _event, w=widget: self._freeze_selection_updates(w), add="+")
        widget.bind("<ButtonRelease-1>", lambda _event, w=widget: self._release_selection_updates(w), add="+")

    def _toggle_retrieved_knowledge_panel(self):
        if self._retrieved_knowledge_visible:
            self.retrieved_knowledge_display.pack_forget()
            self._retrieved_knowledge_visible = False
            return
        self.retrieved_knowledge_display.pack(fill=tk.X, pady=(6, 0))
        self._retrieved_knowledge_visible = True

    def _update_retrieved_knowledge_panel(self, results):
        if not hasattr(self, "retrieved_knowledge_frame"):
            return

        if not results:
            self.retrieved_knowledge_summary_var.set("No snippets")
            self.retrieved_knowledge_display.configure(state=tk.NORMAL)
            self.retrieved_knowledge_display.delete("1.0", tk.END)
            self.retrieved_knowledge_display.configure(state=tk.NORMAL)
            self.retrieved_knowledge_display.pack_forget()
            self._retrieved_knowledge_visible = False
            return

        if not self._retrieved_knowledge_visible:
            self.retrieved_knowledge_display.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
            self._retrieved_knowledge_visible = True
        self.retrieved_knowledge_summary_var.set(f"{len(results)} snippet(s)")
        lines = []
        for result in results:
            matched = ", ".join(result.matched_terms) if result.matched_terms else "(none)"
            snippet = result.chunk.text.strip().replace("\n", " ")
            if len(snippet) > 500:
                snippet = snippet[:497].rstrip() + "..."
            lines.append(
                f"{result.chunk.chunk_id} | score={result.score:.3f} | matched={matched}\n{snippet}"
            )

        self.retrieved_knowledge_display.configure(state=tk.NORMAL)
        self.retrieved_knowledge_display.delete("1.0", tk.END)
        self.retrieved_knowledge_display.insert("1.0", "\n\n".join(lines))
        self.retrieved_knowledge_display.configure(state=tk.NORMAL)

    def _bind_system_prompt_editing(self):
        self.system_prompt.bind("<Control-a>", lambda _event: self._select_all_text(self.system_prompt))
        self.system_prompt.bind("<Control-A>", lambda _event: self._select_all_text(self.system_prompt))
        self.system_prompt.bind("<Control-z>", self._undo_system_prompt)
        self.system_prompt.bind("<Control-Z>", self._undo_system_prompt)
        self.system_prompt.bind("<Control-y>", self._redo_system_prompt)
        self.system_prompt.bind("<Control-Y>", self._redo_system_prompt)
        self.system_prompt.bind("<Control-Shift-Z>", self._redo_system_prompt)

    def _undo_system_prompt(self, _event=None):
        try:
            self.system_prompt.edit_undo()
            self.system_prompt.edit_modified(True)
            self.root.after_idle(self._fit_system_prompt_to_content)
        except tk.TclError:
            pass
        return "break"

    def _redo_system_prompt(self, _event=None):
        try:
            self.system_prompt.edit_redo()
            self.system_prompt.edit_modified(True)
            self.root.after_idle(self._fit_system_prompt_to_content)
        except tk.TclError:
            pass
        return "break"

    def _block_readonly_edit(self, event):
        allowed_keys = {
            "Left", "Right", "Up", "Down", "Prior", "Next", "Home", "End",
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
            "Escape",
        }
        is_ctrl = bool(event.state & 0x4)
        if is_ctrl and event.keysym.lower() in {"a", "c", "insert"}:
            return None
        if event.keysym in allowed_keys:
            return None
        return "break"

    def _select_all_text(self, widget: tk.Text):
        self._freeze_selection_updates(widget)
        widget.tag_add(tk.SEL, "1.0", tk.END)
        widget.mark_set(tk.INSERT, "1.0")
        widget.see(tk.INSERT)
        return "break"

    # ── Theme ───────────────────────────────────────────────────────────

    def _toggle_theme(self):
        self.is_dark = not self.is_dark
        sv_ttk.set_theme("dark" if self.is_dark else "light")
        self.theme_btn.configure(text="Light Theme" if self.is_dark else "Dark Theme")
        self._apply_theme()

    def _apply_theme(self):
        palette = THEMES["dark" if self.is_dark else "light"]
        style = ttk.Style()
        self.root.configure(bg=palette["window_bg"])
        style.configure("App.TFrame", background=palette["window_bg"])
        style.configure("Header.TFrame", background=palette["surface"])
        style.configure("Panel.TFrame", background=palette["surface"])
        style.configure("Params.TFrame", background=palette["surface_alt"])
        style.configure("Input.TFrame", background=palette["surface"])
        style.configure("Status.TFrame", background=palette["surface_alt"])
        style.configure("Sidebar.TFrame", background=palette["surface_alt"])
        style.configure(
            "Header.TLabel",
            background=palette["surface"],
            foreground=palette["text_fg"],
        )
        style.configure(
            "Title.TLabel",
            background=palette["surface"],
            foreground=palette["text_fg"],
            font=(self.font_family.get(), self.font_size.get() + 4, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=palette["surface"],
            foreground=palette["muted"],
            font=(self.font_family.get(), max(8, self.font_size.get() - 1)),
        )
        style.configure(
            "Section.TLabel",
            background=palette["surface"],
            foreground=palette["text_fg"],
            font=(self.font_family.get(), self.font_size.get(), "bold"),
        )
        style.configure(
            "SidebarTitle.TLabel",
            background=palette["surface_alt"],
            foreground=palette["text_fg"],
            font=(self.font_family.get(), self.font_size.get() + 1, "bold"),
        )
        style.configure(
            "Toolbar.TLabel",
            background=palette["surface"],
            foreground=palette["muted"],
        )
        style.configure(
            "Params.TLabel",
            background=palette["surface_alt"],
            foreground=palette["muted"],
        )
        style.configure(
            "ParamValue.TLabel",
            background=palette["surface_alt"],
            foreground=palette["text_fg"],
            font=(self.font_family.get(), self.font_size.get(), "bold"),
        )
        style.configure(
            "Status.TLabel",
            background=palette["surface_alt"],
            foreground=palette["muted"],
        )
        style.configure(
            "Stats.TLabel",
            background=palette["surface_alt"],
            foreground=palette["stats_fg"],
        )
        style.configure(
            "StatsWarning.TLabel",
            background=palette["surface_alt"],
            foreground="#f59e0b",
        )
        style.configure(
            "StatsCritical.TLabel",
            background=palette["surface_alt"],
            foreground="#f87171",
        )
        style.configure("TPanedwindow", background=palette["window_bg"])
        text_widgets = [
            self.chat_display,
            self.user_input,
            self.system_prompt,
            self.thinking_display,
            self.diagnostics_display,
            self.retrieved_knowledge_display,
        ]
        for w in text_widgets:
            w.configure(
                bg=palette["text_bg"],
                fg=palette["text_fg"],
                insertbackground=palette["insert_bg"],
                selectbackground=palette["select_bg"],
                highlightthickness=1,
                highlightbackground=palette["border"],
                highlightcolor=palette["accent"],
            )
        self.slash_popup.configure(
            bg=palette["surface_alt"],
            fg=palette["text_fg"],
            selectbackground=palette["select_bg"],
            selectforeground=palette["text_fg"],
            highlightthickness=1,
            highlightbackground=palette["border"],
            font=(self.font_family.get(), self.font_size.get()),
        )
        self.progress_bar.set_palette(
            background=palette["surface_alt"],
            track=palette["border"],
            accent=palette["accent"],
        )
        self._configure_chat_tags()

    # ── Fonts ───────────────────────────────────────────────────────────

    def _apply_fonts(self):
        family = self.font_family.get()
        size = self.font_size.get()
        base_font = (family, size)
        for w in [
            self.chat_display,
            self.user_input,
            self.system_prompt,
            self.thinking_display,
            self.diagnostics_display,
            self.retrieved_knowledge_display,
        ]:
            w.configure(font=base_font)
        self._apply_theme()
        self._configure_chat_tags()

    def _configure_chat_tags(self):
        palette = THEMES["dark" if self.is_dark else "light"]
        family = self.font_family.get()
        size = self.font_size.get()

        tags = {
            "user": {"foreground": palette["user"], "font": (family, size, "bold")},
            "assistant": {"foreground": palette["assistant"], "font": (family, size, "bold")},
            "thinking": {"foreground": palette["thinking"], "font": (family, size - 1, "italic")},
            "system_msg": {"foreground": palette["system_msg"], "font": (family, size - 1, "italic")},
            "bold": {"foreground": palette["bold"], "font": (family, size, "bold")},
            "italic": {"foreground": palette["italic"], "font": (family, size, "italic")},
            "h1": {"foreground": palette["heading"], "font": (family, size + 6, "bold")},
            "h2": {"foreground": palette["heading"], "font": (family, size + 4, "bold")},
            "h3": {"foreground": palette["heading"], "font": (family, size + 2, "bold")},
            "h4": {"foreground": palette["heading"], "font": (family, size + 1, "bold")},
            "h5": {"foreground": palette["heading"], "font": (family, size, "bold")},
            "h6": {"foreground": palette["heading"], "font": (family, size, "bold italic")},
            "code_inline": {
                "foreground": palette["code_fg"],
                "background": palette["code_bg"],
                "font": (family, size),
            },
            "code_block": {
                "foreground": palette["code_fg"],
                "background": palette["code_bg"],
                "font": (family, size),
                "lmargin1": 16,
                "lmargin2": 16,
                "rmargin": 16,
            },
            "blockquote": {
                "foreground": palette["blockquote"],
                "font": (family, size, "italic"),
                "lmargin1": 20,
                "lmargin2": 20,
            },
            "stdout": {"foreground": palette["text_fg"], "font": (family, size)},
            "stderr": {"foreground": "#f87171", "font": (family, size)},
            "diagnostic_meta": {
                "foreground": palette["system_msg"],
                "font": (family, size - 1, "italic"),
            },
        }
        for tag_name, opts in tags.items():
            self.chat_display.tag_configure(tag_name, **opts)
            self.thinking_display.tag_configure(tag_name, **opts)
            self.diagnostics_display.tag_configure(tag_name, **opts)
            self.retrieved_knowledge_display.tag_configure(tag_name, **opts)

        self.user_input.tag_configure(
            "slash_command",
            foreground=palette["user"],
            font=(family, size, "bold"),
        )
        self.user_input.tag_configure(
            "slash_command_arg",
            foreground=palette["system_msg"],
            font=(family, size),
        )

    # ── Thinking panel helpers ──────────────────────────────────────────

    def _show_thinking_panel(self):
        if not self._thinking_visible:
            self.chat_pane.insert(0, self.thinking_frame, weight=1)
            self._thinking_visible = True

    def _hide_thinking_panel(self):
        if self._thinking_visible:
            self.chat_pane.remove(self.thinking_frame)
            self._thinking_visible = False

    def _reset_thinking_panel_for_generation(self):
        if self._thinking_render_job:
            try:
                self.root.after_cancel(self._thinking_render_job)
            except tk.TclError:
                pass
            self._thinking_render_job = None
        self._thinking_stream.reset()
        self._stream_thinking_text = ""
        self.thinking_display.configure(state=tk.NORMAL)
        self.thinking_display.delete("1.0", tk.END)
        self.thinking_display.configure(state=tk.NORMAL)
        self._active_thinking_block = False
        self._has_thinking_history = False
        self._hide_thinking_panel()

    def _on_thinking_mode_changed(self):
        self._schedule_token_usage_update()
        self._refresh_context_strip()
        if self.think_var.get():
            self.status_var.set("Thinking mode on.")
            return

        if self._thinking_render_job:
            try:
                self.root.after_cancel(self._thinking_render_job)
            except tk.TclError:
                pass
            self._thinking_render_job = None
        self._active_thinking_block = False
        self._hide_thinking_panel()
        self.status_var.set("Thinking mode off.")

    def _toggle_behaviour_panel(self):
        self._select_sidebar_section("behaviour")

    def _toggle_diagnostics_panel(self):
        self._select_sidebar_section("diagnostics")
        self.diagnostics_display.see(tk.END)

    def _make_generation_slider(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.Variable,
        default: float,
        from_: float,
        to: float,
        resolution: float,
        formatter,
        integer: bool = False,
        expand: bool = False,
    ):
        frame = ttk.Frame(parent, style="Params.TFrame")
        frame.pack(fill=tk.X, expand=expand, pady=(0, 12))

        header = ttk.Frame(frame, style="Params.TFrame")
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text=label,
            style="Params.TLabel",
            wraplength=260,
            justify=tk.LEFT,
        ).pack(side=tk.LEFT)

        value_var = tk.StringVar(value=formatter(float(variable.get())))
        ttk.Label(
            header,
            textvariable=value_var,
            style="ParamValue.TLabel",
            width=18,
            anchor=tk.E,
        ).pack(side=tk.RIGHT)

        def on_change(raw_value):
            value = float(raw_value)
            snapped = round((value - from_) / resolution) * resolution + from_
            snapped = max(from_, min(to, snapped))
            if integer:
                snapped = int(round(snapped))
            else:
                snapped = round(snapped, 4)
            changed = variable.get() != snapped
            if changed:
                variable.set(snapped)
            value_var.set(formatter(float(snapped)))
            if (
                changed
                and not self._suppress_generation_status
                and not self.generating
                and not self.updating_behaviour
            ):
                self.status_var.set(
                    "Generation settings updated. Sampling range and reply length can affect response time."
                )

        scale = ttk.Scale(
            frame,
            from_=from_,
            to=to,
            variable=variable,
            command=on_change,
        )
        scale.pack(fill=tk.X, pady=(4, 0))
        self._generation_sliders.append(scale)
        self._generation_controls.append(
            {
                "variable": variable,
                "default": default,
                "formatter": formatter,
                "value_var": value_var,
                "integer": integer,
            }
        )

    def _reset_generation_settings(self):
        if self.generating or self.updating_behaviour:
            return

        self._suppress_generation_status = True
        try:
            for control in self._generation_controls:
                value = control["default"]
                if control["integer"]:
                    value = int(value)
                control["variable"].set(value)
                control["value_var"].set(control["formatter"](float(value)))
        finally:
            self._suppress_generation_status = False

        self._schedule_token_usage_update()
        self.status_var.set("Generation settings reset to defaults.")

    def _refresh_generation_slider_state(self):
        state = ["disabled"] if self.generating or self.updating_behaviour else ["!disabled"]
        for scale in self._generation_sliders:
            scale.state(state)

    def _creativity_label(self, value: float) -> str:
        if value < 0.5:
            return "Precise"
        if value < 0.9:
            return "Focused"
        if value < 1.2:
            return "Balanced"
        if value < 1.6:
            return "Creative"
        return "Experimental"

    def _variety_label(self, value: float) -> str:
        if value < 0.55:
            return "Very steady"
        if value < 0.85:
            return "Steady"
        if value < 1.0:
            return "Varied"
        return "Most varied"

    def _choice_pool_label(self, value: float) -> str:
        if value <= 10:
            return "Very limited"
        if value <= 40:
            return "Limited"
        if value <= 100:
            return "Flexible"
        return "Very flexible"

    def _reply_length_label(self, value: float) -> str:
        if value <= 512:
            return "Short"
        if value <= 1536:
            return "Medium"
        if value <= 4096:
            return "Long"
        return "Very long"

    def _copy_latest_response(self):
        text = self._stream_response_text.strip()
        if not text:
            for message in reversed(self.messages):
                if message.get("role") == "assistant":
                    text = str(message.get("content", "")).strip()
                    break

        if not text:
            self.status_var.set("No assistant response to copy.")
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("Latest assistant response copied.")

    def _assistant_display_name(self) -> str:
        option = getattr(self, "active_model_option", None)
        if option is None:
            option = get_model_option(getattr(self, "selected_model_id", None))
        return option.display_name

    def _assistant_label(self) -> str:
        return f"{self._assistant_display_name()}: "

    def _show_status_progress(self):
        if not self._status_progress_visible:
            self.progress_bar.pack(side=tk.LEFT, padx=(0, 10), before=self.elapsed_label)
            self._status_progress_visible = True

    def _hide_status_progress(self):
        if self._status_progress_visible:
            self.progress_bar.pack_forget()
            self._status_progress_visible = False

    def _hide_loading_screen(self):
        if not self._loading_screen_visible:
            return

        try:
            self.chat_pane.remove(self.loading_frame)
        except tk.TclError:
            pass
        self.chat_pane.add(self.main_chat_frame, weight=3)
        self._loading_screen_visible = False

    def _model_choice_labels(self) -> list[str]:
        self._model_label_to_id = {
            (
            f"{option.family.title()}: {option.display_name} - {option.context_length} - "
                f"{self._model_cache_status_label(option.model_id)}"
            ): option.model_id
            for option in MODEL_CATALOG
        }
        return list(self._model_label_to_id.keys())

    def _model_is_downloaded(self, model_id: str) -> bool:
        try:
            cached = try_to_load_from_cache(model_id, "config.json")
        except Exception:
            return False
        return isinstance(cached, str)

    def _model_cache_status_label(self, model_id: str) -> str:
        parts = ["downloaded" if self._model_is_downloaded(model_id) else "not downloaded"]
        if valid_model_id_or_default(self.selected_model_id) == model_id:
            parts.append("last used")
        return ", ".join(parts)

    def _thinking_format_label(self, option) -> str:
        if option.thinking_parser == "qwen_think_tags":
            return "Qwen <think>...</think> blocks; needs Qwen3-capable Transformers."
        return "Gemma channel markers."

    def _model_label_for_id(self, model_id: str) -> str:
        selected = valid_model_id_or_default(model_id)
        for label, option_id in self._model_label_to_id.items():
            if option_id == selected:
                return label
        labels = self._model_choice_labels()
        for label, option_id in self._model_label_to_id.items():
            if option_id == selected:
                return label
        return labels[0]

    def _prompt_for_startup_model(self):
        labels = self._model_choice_labels()
        current_id = valid_model_id_or_default(self.selected_model_id)
        self.selected_model_var.set(self._model_label_for_id(current_id))

        dialog = tk.Toplevel(self.root)
        dialog.title("Choose Model")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=(22, 18), style="Panel.TFrame")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Choose a local model",
            style="Section.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))

        ttk.Label(
            frame,
            text=(
                "All listed models support switchable Thinking Mode. Larger models "
                "may require much more VRAM, disk space, download time, and load time."
            ),
            wraplength=560,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(0, 12))

        combo = ttk.Combobox(
            frame,
            textvariable=self.selected_model_var,
            values=labels,
            width=56,
            state="readonly",
        )
        combo.pack(fill=tk.X, pady=(0, 10))

        detail_var = tk.StringVar()
        ttk.Label(
            frame,
            textvariable=detail_var,
            wraplength=560,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(0, 16))

        def refresh_detail(_event=None):
            option_id = self._model_label_to_id.get(self.selected_model_var.get(), current_id)
            option = get_model_option(option_id)
            status = self._model_cache_status_label(option.model_id)
            detail_var.set(
                f"{option.model_id}\n"
                f"Status: {status}\n"
                f"Family: {option.family.title()}\n"
                f"Context: {option.context_length}\n"
                f"Thinking format: {self._thinking_format_label(option)}\n"
                f"{option.notes}\n"
                f"{option.vram_warning}"
            )

        def choose():
            option_id = self._model_label_to_id.get(self.selected_model_var.get(), current_id)
            self.selected_model_id = valid_model_id_or_default(option_id)
            if not get_model_option(self.selected_model_id).supports_thinking:
                self.think_var.set(False)
            self._save_selected_model_id(self.selected_model_id)
            dialog.grab_release()
            dialog.destroy()
            self._finish_startup_after_model_choice()

        button_row = ttk.Frame(frame, style="Panel.TFrame")
        button_row.pack(fill=tk.X)
        ttk.Button(
            button_row,
            text="Load selected model",
            command=choose,
        ).pack(side=tk.RIGHT)

        combo.bind("<<ComboboxSelected>>", refresh_detail)
        dialog.protocol("WM_DELETE_WINDOW", choose)
        refresh_detail()

        dialog.update_idletasks()
        width = dialog.winfo_width()
        height = dialog.winfo_height()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.lift()
        combo.focus_set()

    def _begin_thinking_block(self):
        self._show_thinking_panel()
        self.thinking_display.configure(state=tk.NORMAL)
        self.thinking_display.mark_set("thinking_block_start", tk.END)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.thinking_display.insert(tk.END, f"Thinking - {timestamp}\n\n", "thinking")
        self._thinking_stream.reset()
        self.thinking_display.mark_set("thinking_stream_start", "end-1c")
        self.thinking_display.mark_gravity("thinking_stream_start", tk.LEFT)
        self.thinking_display.mark_set("thinking_live_tail_start", "end-1c")
        self.thinking_display.mark_gravity("thinking_live_tail_start", tk.LEFT)
        self.thinking_display.configure(state=tk.NORMAL)
        self._active_thinking_block = True
        self._has_thinking_history = True
        self.thinking_display.see(tk.END)

    def _discard_active_thinking_block(self):
        if not self._active_thinking_block:
            return

        self.thinking_display.configure(state=tk.NORMAL)
        try:
            self.thinking_display.delete("thinking_block_start", tk.END)
        except tk.TclError:
            pass
        self.thinking_display.configure(state=tk.NORMAL)
        self._active_thinking_block = False
        self._has_thinking_history = bool(
            self.thinking_display.get("1.0", "end-1c").strip()
        )
        if not self._has_thinking_history:
            self._hide_thinking_panel()

