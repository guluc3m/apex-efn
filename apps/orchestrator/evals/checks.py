"""Deterministic checks for golden cases. No LLM judge: every check is code.

A case's ``expect`` is a list of single-key mappings, for example ``{equals: {top_offer_id: "o1"}}``.
"""

from __future__ import annotations

import json
import re
from typing import Any

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [t for item in value for t in _texts(item)]
    if isinstance(value, dict):
        return [t for item in value.values() for t in _texts(item)]
    return []


def run_check(kind: str, arg: Any, output: dict[str, Any], input_text: str) -> str | None:
    """Return ``None`` when the check passes, otherwise a short failure reason."""
    if kind == "equals":
        for field, want in arg.items():
            if output.get(field) != want:
                return f"{field}: expected {want!r}, got {output.get(field)!r}"
        return None
    if kind == "is_null":
        for field in arg:
            if output.get(field) is not None:
                return f"{field}: expected null, got {output.get(field)!r}"
        return None
    if kind == "contains_all":
        for field, wanted in arg.items():
            have = output.get(field) or []
            for item in wanted:
                if item not in have:
                    return f"{field}: missing {item!r}"
        return None
    if kind == "list_subset_of":
        for field, allowed in arg.items():
            for item in output.get(field) or []:
                value = item.get("platform_id") if isinstance(item, dict) else item
                if value not in allowed:
                    return f"{field}: {value!r} not in allowed {allowed}"
        return None
    if kind == "min_len":
        for field, size in arg.items():
            if len(output.get(field) or []) < size:
                return f"{field}: expected at least {size} items"
        return None
    if kind == "max_len":
        for field, size in arg.items():
            if len(output.get(field) or []) > size:
                return f"{field}: expected at most {size} items"
        return None
    if kind == "numbers_in_input":
        allowed = _numbers(input_text)
        for field in arg:
            for text in _texts(output.get(field)):
                invented = _numbers(text) - allowed
                if invented:
                    return f"{field}: numbers not in input: {sorted(invented)}"
        return None
    if kind == "mentions_all":
        text = json.dumps(output, ensure_ascii=False)
        for needle in arg:
            if needle not in text:
                return f"output does not mention {needle!r}"
        return None
    return f"unknown check: {kind}"


__all__ = ["run_check"]
