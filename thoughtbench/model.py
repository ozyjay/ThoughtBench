"""Model stream and thinking parser helpers."""

import re
import threading
from dataclasses import dataclass


class _StopOnEvent:
    """Tells model.generate() to stop when a threading.Event is set."""

    def __init__(self, event: threading.Event):
        self._event = event

    def __call__(self, input_ids, scores, **kwargs):
        return self._event.is_set()


@dataclass(frozen=True)
class ParsedModelResponse:
    thinking: str | None
    content: str


def strip_chat_special_tokens(text: str) -> str:
    cleaned = text or ""
    for token in (
        "<|im_end|>",
        "<|im_start|>",
        "<|endoftext|>",
    ):
        cleaned = cleaned.replace(token, "")
    return cleaned.strip()


def _split_gemma_channels(raw_text: str) -> tuple[str | None, str]:
    """Split Gemma thinking-mode output into thinking and final response."""
    text = raw_text or ""
    text = text.replace("<|turn>", "").replace("<turn|>", "")
    channel_re = re.compile(
        r"<\|channel\|?>\s*(thought|thinking|analysis|response|final|answer)|"
        r"<(thought|thinking|analysis|response|final|answer)\|>|"
        r"<channel\|>",
        re.IGNORECASE,
    )

    matches = list(channel_re.finditer(text))
    if not matches:
        return None, strip_chat_special_tokens(text)

    thinking_parts: list[str] = []
    response_parts: list[str] = []
    current = "response"

    for index, match in enumerate(matches):
        channel = (match.group(1) or match.group(2) or "").lower()
        if channel in {"thought", "thinking", "analysis"}:
            current = "thinking"
        elif channel in {"response", "final", "answer"} or match.group(0) == "<channel|>":
            current = "response"

        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[start:end]
        if current == "thinking":
            thinking_parts.append(segment)
        else:
            response_parts.append(segment)

    return (
        strip_chat_special_tokens("".join(thinking_parts)) or None,
        strip_chat_special_tokens("".join(response_parts)),
    )


def _split_qwen_think_tags(raw_text: str) -> tuple[str | None, str]:
    text = strip_chat_special_tokens(raw_text)
    if not text:
        return None, ""

    close_match = re.search(r"</think>", text, re.IGNORECASE)
    if not close_match:
        cleaned = re.sub(r"<think>\s*", "", text, count=1, flags=re.IGNORECASE)
        return None, strip_chat_special_tokens(cleaned)

    thinking = text[:close_match.start()]
    thinking = re.sub(r"^\s*<think>\s*", "", thinking, count=1, flags=re.IGNORECASE)
    response = text[close_match.end():]
    return (
        strip_chat_special_tokens(thinking) or None,
        strip_chat_special_tokens(response),
    )


def split_model_response(raw_text: str, model_option) -> ParsedModelResponse:
    parser = getattr(model_option, "thinking_parser", "gemma_channels")
    if parser == "qwen_think_tags":
        thinking, content = _split_qwen_think_tags(raw_text)
    else:
        thinking, content = _split_gemma_channels(raw_text)
    return ParsedModelResponse(thinking=thinking, content=content)
