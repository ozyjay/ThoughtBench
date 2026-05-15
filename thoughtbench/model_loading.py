"""Shared model loading helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import torch
from transformers import AutoModelForCausalLM, AutoProcessor, AutoTokenizer

from .config import ModelOption, get_model_option


LoadMode = Literal["auto", "bf16", "4bit"]


@dataclass(frozen=True)
class ModelLoadInfo:
    mode: str
    dtype: torch.dtype
    total_vram_gb: float | None
    detail: str


@dataclass
class ChatModelAdapter:
    raw: object
    loader_kind: str

    @property
    def tokenizer(self):
        if self.loader_kind == "processor":
            return getattr(self.raw, "tokenizer", self.raw)
        return self.raw

    def apply_chat_template(self, *args, **kwargs):
        return self.raw.apply_chat_template(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self.loader_kind == "tokenizer" and "text" in kwargs:
            text = kwargs.pop("text")
            return self.raw(text, *args, **kwargs)
        return self.raw(*args, **kwargs)

    def decode(self, *args, **kwargs):
        target = self.raw if hasattr(self.raw, "decode") else self.tokenizer
        return target.decode(*args, **kwargs)


def _normalise_load_mode(value: str | None) -> LoadMode:
    mode = (value or "auto").strip().lower()
    aliases = {
        "default": "auto",
        "normal": "bf16",
        "fp16": "bf16",
        "float16": "bf16",
        "low-vram": "4bit",
        "low_vram": "4bit",
        "quantized": "4bit",
        "quantised": "4bit",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"auto", "bf16", "4bit"}:
        return "auto"
    return mode  # type: ignore[return-value]


def _cuda_total_vram_gb() -> float | None:
    if not torch.cuda.is_available():
        return None
    props = torch.cuda.get_device_properties(0)
    return round(props.total_memory / (1024**3), 1)


def _preferred_dtype() -> torch.dtype:
    if torch.cuda.is_available():
        major, _minor = torch.cuda.get_device_capability(0)
        if major < 8:
            return torch.float16
    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    # Apple Silicon MPS: bfloat16 supported since PyTorch 2.x
    if torch.backends.mps.is_available():
        return torch.bfloat16
    return torch.float16


def choose_load_mode(requested: str | None = None) -> tuple[LoadMode, torch.dtype, float | None]:
    mode = _normalise_load_mode(
        requested
        or os.environ.get("THOUGHTBENCH_LOAD_MODE")
        or os.environ.get("GEMMA4_LOAD_MODE")
    )
    dtype = _preferred_dtype()
    total_vram_gb = _cuda_total_vram_gb()
    if mode == "auto" and total_vram_gb is not None and total_vram_gb < 12:
        mode = "4bit"
    return mode, dtype, total_vram_gb


def build_model_load_kwargs(mode: str | None = None) -> tuple[dict, ModelLoadInfo]:
    selected_mode, dtype, total_vram_gb = choose_load_mode(mode)
    kwargs: dict = {}

    if selected_mode == "4bit":
        try:
            from transformers import BitsAndBytesConfig
        except ImportError as exc:
            raise RuntimeError(
                "Low-VRAM mode needs a recent transformers install with BitsAndBytesConfig."
            ) from exc

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=dtype,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        kwargs["device_map"] = {"": 0} if torch.cuda.is_available() else "auto"
        detail = "4-bit low-VRAM load"    elif torch.backends.mps.is_available() and not torch.cuda.is_available():
        # Apple Silicon: route entire model to MPS.
        # device_map="auto" with accelerate resolves to CPU on macOS;
        # explicitly targeting mps gives Metal-backed inference.
        kwargs["device_map"] = {"" : "mps"}
        kwargs["dtype"] = dtype
        detail = "MPS (Apple Silicon) load"    else:
        kwargs["device_map"] = "auto"
        kwargs["dtype"] = dtype
        detail = "BF16/FP16 load"

    if total_vram_gb is not None:
        detail = f"{detail} on {total_vram_gb} GB VRAM"

    return kwargs, ModelLoadInfo(
        mode=selected_mode,
        dtype=dtype,
        total_vram_gb=total_vram_gb,
        detail=detail,
    )


def load_processor_and_model(
    model_path_or_id: str | Path,
    mode: str | None = None,
    model_option: ModelOption | None = None,
):
    option = model_option or get_model_option(str(model_path_or_id))
    if option.loader_kind == "tokenizer":
        processor = ChatModelAdapter(
            AutoTokenizer.from_pretrained(model_path_or_id),
            option.loader_kind,
        )
    else:
        processor = ChatModelAdapter(
            AutoProcessor.from_pretrained(model_path_or_id),
            option.loader_kind,
        )
    kwargs, load_info = build_model_load_kwargs(mode)
    try:
        model = AutoModelForCausalLM.from_pretrained(model_path_or_id, **kwargs)
    except Exception as exc:
        if load_info.mode == "4bit":
            raise RuntimeError(
                "Low-VRAM 4-bit load failed. Make sure bitsandbytes installed correctly, "
                "or set THOUGHTBENCH_LOAD_MODE=bf16 on a larger GPU."
            ) from exc
        raise
    return processor, model, load_info


def model_input_device(model) -> torch.device:
    device_map = getattr(model, "hf_device_map", None)
    if isinstance(device_map, dict):
        for device in device_map.values():
            if isinstance(device, str) and device not in {"cpu", "disk"}:
                return torch.device(device)
            if isinstance(device, int):
                return torch.device(f"cuda:{device}")
    if torch.backends.mps.is_available() and not torch.cuda.is_available():
        return torch.device("mps")
    return getattr(model, "device", torch.device("cuda" if torch.cuda.is_available() else "cpu"))
