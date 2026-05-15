"""Shared model loading helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import torch
from transformers import AutoModelForCausalLM, AutoProcessor, AutoTokenizer

from .config import ModelOption, get_model_option


LoadMode = Literal["auto", "bf16"]


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
    }
    mode = aliases.get(mode, mode)
    if mode not in {"auto", "bf16"}:
        return "auto"
    return mode  # type: ignore[return-value]


def _preferred_dtype() -> torch.dtype:
    # Apple Silicon MPS: bfloat16 supported since PyTorch 2.x
    if torch.backends.mps.is_available():
        return torch.bfloat16
    return torch.float16


def choose_load_mode(requested: str | None = None) -> tuple[LoadMode, torch.dtype, float | None]:
    mode = _normalise_load_mode(
        requested
        or os.environ.get("THOUGHTBENCH_LOAD_MODE")
    )
    dtype = _preferred_dtype()
    return mode, dtype, None


def build_model_load_kwargs(mode: str | None = None) -> tuple[dict, ModelLoadInfo]:
    selected_mode, dtype, total_vram_gb = choose_load_mode(mode)
    kwargs: dict = {}

    if torch.backends.mps.is_available():
        # Apple Silicon: route entire model to MPS.
        # device_map="auto" with accelerate resolves to CPU on macOS;
        # explicitly targeting mps gives Metal-backed inference.
        kwargs["device_map"] = {"": "mps"}
        kwargs["dtype"] = dtype
        detail = "MPS (Apple Silicon) load"
    else:
        kwargs["device_map"] = "auto"
        kwargs["dtype"] = dtype
        detail = "BF16/FP16 load"

    return kwargs, ModelLoadInfo(
        mode=selected_mode,
        dtype=dtype,
        total_vram_gb=None,
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
    model = AutoModelForCausalLM.from_pretrained(model_path_or_id, **kwargs)
    return processor, model, load_info


def model_input_device(model) -> torch.device:
    device_map = getattr(model, "hf_device_map", None)
    if isinstance(device_map, dict):
        for device in device_map.values():
            if isinstance(device, str) and device not in {"cpu", "disk"}:
                return torch.device(device)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return getattr(model, "device", torch.device("cpu"))
