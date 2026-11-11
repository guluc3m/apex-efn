"""Deterministic helpers: token usage approximation, embeddings, and content rendering."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from typing import Any

from llm_stub.models import ChatMessage

# Usage approximation (documented in README):
#   prompt_tokens     = sum over messages of (4 + ceil(chars / 4)) of the message text
#   completion_tokens = ceil(chars / 4) of the produced content (min 1 when non-empty)
# This is a deterministic stand-in for a real tokenizer, not an exact count.


def approx_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            else:
                parts.append(json.dumps(part, sort_keys=True, default=str))
        return "".join(parts)
    return json.dumps(content, sort_keys=True, default=str)


def prompt_tokens(messages: list[ChatMessage]) -> int:
    total = 0
    for m in messages:
        # +4 per message overhead, mirroring the OpenAI chat-format accounting shape.
        total += 4 + approx_tokens(content_to_text(m.content))
    return total


def usage_block(
    prompt: int, completion: int, override: dict[str, int] | None = None
) -> dict[str, int]:
    usage = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }
    if override:
        usage.update(override)
        usage["total_tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    return usage


def render_content(value: Any) -> str:
    """Render a scripted response payload into the string the model 'emits'."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def deterministic_embedding(text: str, dim: int) -> list[float]:
    """Unit-length vector derived from sha256 of the input. Same input -> same vector."""
    out: list[float] = []
    counter = 0
    while len(out) < dim:
        digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
        for (value,) in struct.iter_unpack("<I", digest):
            out.append(value / 0xFFFFFFFF * 2.0 - 1.0)
            if len(out) == dim:
                break
        counter += 1
    norm = math.sqrt(sum(v * v for v in out)) or 1.0
    return [round(v / norm, 8) for v in out]


_MONEY_RE = re.compile(
    r"\b(EUR|USD|CNY|GBP)\s?(\d+(?:[.,]\d{2})?)|(\d+(?:[.,]\d{2})?)\s?(EUR|USD|CNY|GBP)\b"
)


def extract_money(text: str) -> str | None:
    """The first ``CUR amount`` or ``amount CUR`` pair in ``text``, normalised to ``CUR 4.10``."""
    match = _MONEY_RE.search(text)
    if match is None:
        return None
    currency = match.group(1) or match.group(4)
    amount = (match.group(2) or match.group(3)).replace(",", ".")
    return f"{currency} {amount}"


def echo_price_text(
    messages: list[ChatMessage],
    *,
    role: str = "seller",
    fallback: str | None = None,
) -> str:
    """A sentence in the requested voice that repeats the price the prompt states, if any."""
    if fallback is None:
        fallback = (
            "Hello, could you share your volume tiers and best unit price for this order?"
            if role == "buyer"
            else "Thanks for the message, let me check with the factory and come back to you."
        )
    for message in reversed(messages):
        money = extract_money(content_to_text(message.content))
        if money is not None:
            if role == "buyer":
                return f"We can offer {money} per unit for that volume. Would that work for you?"
            return f"Understood. We can do {money} per unit for that volume."
    return fallback
