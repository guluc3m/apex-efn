"""Pure resolution: layers → effective configuration with provenance (ADR-400 §1-§2, §4).

Everything here is deterministic and takes no clock: ``resolved_at`` is supplied by the caller.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from apex.tenant_config.errors import ConfigKeyUnset

Json = dict[str, Any]


class Layer(StrEnum):
    GLOBAL = "global"
    TENANT = "tenant"
    CATEGORY = "category"


@dataclass(frozen=True, slots=True)
class ResolvedValue:
    """One leaf of the effective configuration with its provenance."""

    path: str
    value: Any
    layer: Layer
    unset: bool

    def require(self) -> Any:
        """Return the value, or raise ``ConfigKeyUnset``. Never substitutes a default."""
        if self.unset:
            raise ConfigKeyUnset(self.path, scope=self.layer.value)
        return self.value


@dataclass(frozen=True, slots=True)
class EffectiveConfig:
    tenant_id: str
    category: str | None
    config_version: int
    content_hash: str
    resolved_at: datetime
    values: Mapping[str, ResolvedValue] = field(default_factory=dict)

    def get(self, path: str) -> ResolvedValue:
        """Dotted-path lookup. Missing paths are a programming error, not an unset value."""
        try:
            return self.values[path]
        except KeyError as exc:
            raise KeyError(f"unknown config path: {path}") from exc

    def require(self, path: str) -> Any:
        """Typed-consumer accessor: loud on unset keys (ADR-400 §3)."""
        return self.get(path).require()

    def plain(self) -> Json:
        """Effective values as a nested dict (unset keys are ``None``). Used for hashing."""
        out: Json = {}
        for path, rv in self.values.items():
            _set_path(out, path, None if rv.unset else rv.value)
        return out


def _set_path(root: Json, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = root
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def deep_merge(base: Json, patch: Mapping[str, Any]) -> Json:
    """Deep-merge ``patch`` onto ``base`` (ADR-400 §2).

    Objects merge recursively; scalars and arrays replace; an explicit ``None`` replaces the value
    with ``None`` (unset). Pure: neither argument is mutated.
    """
    out: Json = {}
    for key, value in base.items():
        out[key] = _copy(value)
    for key, value in patch.items():
        if isinstance(value, Mapping) and not value and isinstance(out.get(key), dict):
            # An empty object in the patch merges nothing (ADR-400 §2): it does not erase the subtree.
            continue
        if isinstance(value, Mapping) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        elif isinstance(value, Mapping):
            out[key] = deep_merge({}, value)
        else:
            out[key] = _copy(value)
    return out


def _copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy(v) for v in value]
    return value


def canonical_json(data: Any) -> bytes:
    """Canonical JSON bytes for hashing.

    Sorted keys, no insignificant whitespace, UTF-8, no NaN/Infinity. This is a stand-in for
    RFC 8785 JCS (D2-06); once ``apex.signing.jcs`` exists it must be replaced by that implementation
    and the hash test vectors regenerated.
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_hash(effective_plain: Json) -> str:
    """``sha256:<hex>`` over the canonical JSON of the effective values (ADR-400 §4)."""
    return "sha256:" + hashlib.sha256(canonical_json(effective_plain)).hexdigest()


def flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested mapping to dotted leaves. Lists and ``None`` are leaves."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping) and value:
            out.update(flatten(value, path))
        else:
            out[path] = value
    return out
