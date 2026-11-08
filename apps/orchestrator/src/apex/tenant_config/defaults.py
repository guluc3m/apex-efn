"""Loads the versioned global defaults (``config/defaults/tenant-config.v1.json``).

The file uses ``{value, scope, status?, ...}`` leaves for documentation purposes. Only ``value`` is the
config; ``scope``/``status``/``allowed``/``non_configurable``/``pending`` are metadata and are stripped
here. The result is the *global* layer: a plain nested mapping whose unset keys are ``None``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

_META_KEYS: Final[frozenset[str]] = frozenset(
    {"scope", "status", "allowed", "non_configurable", "pending", "note"}
)

DEFAULT_PATH: Final[Path] = (
    Path(__file__).resolve().parents[5] / "config" / "defaults" / "tenant-config.v1.json"
)
"""``apps/orchestrator/src/apex/tenant_config/defaults.py`` → parents[5] is the repo root."""


def _strip(node: Any) -> Any:
    if isinstance(node, dict) and "value" in node and set(node) <= _META_KEYS | {"value"}:
        return node["value"]
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in node.items()}
    return node


def load_global_layer(path: Path = DEFAULT_PATH) -> tuple[int, dict[str, Any]]:
    """Return ``(config_version, plain_global_values)`` from the defaults file."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    version = int(raw["config_version"])
    values = _strip(raw["values"])
    if not isinstance(values, dict):
        raise ValueError("defaults file 'values' must be an object")
    return version, values


def scope_of(path: Path = DEFAULT_PATH) -> dict[str, str]:
    """Map dotted key → declared scope (``global|tenant|category|tenant_category``)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict) and "scope" in node and "value" in node:
            out[prefix] = str(node["scope"])
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{prefix}.{k}" if prefix else k)

    walk(raw["values"], "")
    return out
