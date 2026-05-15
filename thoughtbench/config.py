"""Application constants and theme palettes."""

import sys
from dataclasses import dataclass
from pathlib import Path


def _settings_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Thoughtbench"
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Roaming" / "Thoughtbench"
    # Linux / other
    return Path.home() / ".config" / "Thoughtbench"


@dataclass(frozen=True)
class ModelOption:
    model_id: str
    display_name: str
    context_length: str
    notes: str
    vram_warning: str
    family: str = "gemma"
    loader_kind: str = "processor"
    thinking_parser: str = "gemma_channels"
    supports_thinking: bool = True


DEFAULT_MODEL_ID = "google/gemma-4-E2B-it"
APP_NAME = "Thoughtbench"
MODEL_CATALOG: tuple[ModelOption, ...] = (
    ModelOption(
        model_id="google/gemma-4-E2B-it",
        display_name="Gemma 4 E2B-it",
        context_length="128K tokens",
        notes="Smallest official Gemma 4 instruction model; best default for local testing.",
        vram_warning="Recommended for 8-12 GB VRAM systems; still needs several GB of disk cache.",
    ),
    ModelOption(
        model_id="google/gemma-4-E4B-it",
        display_name="Gemma 4 E4B-it",
        context_length="128K tokens",
        notes="Larger edge model with stronger quality than E2B.",
        vram_warning="Expect higher VRAM, disk, and load time than E2B.",
    ),
    ModelOption(
        model_id="google/gemma-4-26B-A4B-it",
        display_name="Gemma 4 26B A4B-it",
        context_length="256K tokens",
        notes="Mixture-of-experts model with about 3.8B active parameters.",
        vram_warning="Large download and memory footprint; may not fit consumer GPUs without quantization.",
    ),
    ModelOption(
        model_id="google/gemma-4-31B-it",
        display_name="Gemma 4 31B-it",
        context_length="256K tokens",
        notes="Largest curated dense model for highest quality.",
        vram_warning="Very large download and VRAM requirement; intended for high-end systems.",
    ),
    ModelOption(
        model_id="Qwen/Qwen3-0.6B",
        display_name="Qwen3 0.6B",
        context_length="32K tokens",
        notes="Smallest Qwen3 thinking-capable model; useful for quick smoke tests.",
        vram_warning="Lightweight compared with the larger Qwen options, but still downloads into the Hugging Face cache.",
        family="qwen",
        loader_kind="tokenizer",
        thinking_parser="qwen_think_tags",
    ),
    ModelOption(
        model_id="Qwen/Qwen3-1.7B",
        display_name="Qwen3 1.7B",
        context_length="32K tokens",
        notes="Small practical Qwen3 model for local thinking/non-thinking comparisons.",
        vram_warning="Expected to be comfortable on most CUDA systems supported by this app.",
        family="qwen",
        loader_kind="tokenizer",
        thinking_parser="qwen_think_tags",
    ),
    ModelOption(
        model_id="Qwen/Qwen3-4B",
        display_name="Qwen3 4B",
        context_length="32K tokens",
        notes="Balanced Qwen3 option for local evaluation.",
        vram_warning="Higher VRAM and disk use than the smaller Qwen models.",
        family="qwen",
        loader_kind="tokenizer",
        thinking_parser="qwen_think_tags",
    ),
    ModelOption(
        model_id="Qwen/Qwen3-8B",
        display_name="Qwen3 8B",
        context_length="128K tokens",
        notes="Strongest practical Qwen3 option in this app's curated local set.",
        vram_warning="May be tight or slow on 12 GB VRAM, especially with long Thinking Mode outputs.",
        family="qwen",
        loader_kind="tokenizer",
        thinking_parser="qwen_think_tags",
    ),
)
APP_FOLDER_NAME = "thoughtbench"
LEGACY_APP_FOLDER_NAME = ".test.gemma4"
SYSTEM_PROMPT_FILE_NAME = "system_prompt.md"
SYSTEM_PROMPT_HISTORY_FILE_NAME = "system_prompt_history.json"
SYSTEM_PROMPT_HISTORY_LIMIT = 50
CONVERSATION_FILE_NAME = "conversation.json"
SETTINGS_DIR = _settings_dir()
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
LEGACY_SETTINGS_DIR = Path.home() / "AppData" / "Roaming" / "TestGemma4"
LEGACY_SETTINGS_FILE = LEGACY_SETTINGS_DIR / "settings.json"


def get_model_option(model_id: str | None) -> ModelOption:
    selected = valid_model_id_or_default(model_id)
    for option in MODEL_CATALOG:
        if option.model_id == selected:
            return option
    return MODEL_CATALOG[0]


def valid_model_id_or_default(raw: object) -> str:
    if isinstance(raw, str):
        candidate = raw.strip()
        if any(option.model_id == candidate for option in MODEL_CATALOG):
            return candidate
    return DEFAULT_MODEL_ID

THEMES = {
    "dark": {
        "window_bg": "#111318",
        "surface": "#171a21",
        "surface_alt": "#20242d",
        "border": "#2b313d",
        "text_bg": "#1e1e1e",
        "text_fg": "#d4d4d4",
        "insert_bg": "#d4d4d4",
        "select_bg": "#264f78",
        "muted": "#9ca3af",
        "accent": "#38bdf8",
        "user": "#569cd6",
        "assistant": "#6a9955",
        "thinking": "#c586c0",
        "system_msg": "#808080",
        "bold": "#e0e0e0",
        "italic": "#c8c8c8",
        "heading": "#dcdcaa",
        "code_fg": "#ce9178",
        "code_bg": "#2d2d2d",
        "blockquote": "#808080",
        "stats_fg": "#888888",
    },
    "light": {
        "window_bg": "#f5f7fb",
        "surface": "#ffffff",
        "surface_alt": "#eef2f7",
        "border": "#d9e0ea",
        "text_bg": "#ffffff",
        "text_fg": "#1e1e1e",
        "insert_bg": "#1e1e1e",
        "select_bg": "#add6ff",
        "muted": "#64748b",
        "accent": "#0284c7",
        "user": "#2563eb",
        "assistant": "#16a34a",
        "thinking": "#9333ea",
        "system_msg": "#6b7280",
        "bold": "#1e1e1e",
        "italic": "#333333",
        "heading": "#b5651d",
        "code_fg": "#c7254e",
        "code_bg": "#f3f4f6",
        "blockquote": "#6b7280",
        "stats_fg": "#555555",
    },
}
