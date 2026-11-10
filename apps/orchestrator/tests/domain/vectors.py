"""Loader and comparator for the shared domain vectors (ADR-300).

Mirror of ``packages/test-vectors/index.mjs``. This side also validates every file against ``schema.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[4] / "packages" / "test-vectors"
_SAFE = 2**53 - 1
_VALIDATOR = Draft202012Validator(json.loads((ROOT / "schema.json").read_text(encoding="utf-8")))


def _reject_unsafe_integers(value: Any, where: str) -> None:
    # TS reads the same files with JSON.parse, which rounds integers beyond 2^53. Those must be strings.
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > _SAFE:
        raise ValueError(f"{where}: integer {value} is beyond 2^53, write it as a decimal string")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_unsafe_integers(child, f"{where}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _reject_unsafe_integers(child, f"{where}[{i}]")


def load_file(path: Path) -> dict[str, Any]:
    name = path.relative_to(ROOT).as_posix()
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    errors = sorted(_VALIDATOR.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        raise ValueError(f"{name}: {errors[0].message} at {list(errors[0].path)}")
    _reject_unsafe_integers(data, name)
    names = [v["name"] for v in data["vectors"] + data.get("errors", [])]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(f"{name}: duplicate vector names {sorted(duplicates)}")
    data["file"] = name
    data.setdefault("tolerance", 0)
    data.setdefault("errors", [])
    return data


def domain_files(folder: str | None = None) -> list[Path]:
    """Every vector file under ``folder`` (or every folder), never ``signing/`` (DEV-2's own format)."""
    base = ROOT / folder if folder else ROOT
    if not base.is_dir():
        return []
    # Vector files live in a folder per domain; top-level files (package.json, schema.json) are not vectors.
    skip = {"signing", "node_modules"}
    return sorted(
        p
        for p in base.rglob("*.json")
        if len(rel := p.relative_to(ROOT).parts) > 1 and rel[0] not in skip
    )


def cases(folder: str) -> tuple[list[Any], list[Any]]:
    """``(vectors, errors)`` as ``pytest.param(file, vector)`` with ids ``<file>::<name>``."""
    if folder.split("/")[0] == "signing":
        raise ValueError("signing/ has its own format and runners (DEV-2, D2-06)")
    files = [load_file(p) for p in domain_files(folder)]
    if not files:
        raise ValueError(f"no vector files under {folder}/")
    ok = [pytest.param(f, v, id=f"{f['file']}::{v['name']}") for f in files for v in f["vectors"]]
    bad = [pytest.param(f, v, id=f"{f['file']}::{v['name']}") for f in files for v in f["errors"]]
    return ok, bad


def mismatch(actual: Any, expected: Any, tolerance: float = 0, path: str = "$") -> str | None:
    """``None`` on a match, or the first difference. Numbers compare within ``tolerance``, the rest exactly."""
    numbers = (int, float)
    if isinstance(expected, numbers) and not isinstance(expected, bool):
        if (
            isinstance(actual, numbers)
            and not isinstance(actual, bool)
            and abs(actual - expected) <= tolerance
        ):
            return None
        return f"{path}: {actual!r} != {expected!r} (tolerance {tolerance})"
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return f"{path}: expected a list of {len(expected)}"
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            if diff := mismatch(a, e, tolerance, f"{path}[{i}]"):
                return diff
        return None
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return f"{path}: expected an object"
        for key in sorted(set(expected) | set(actual)):
            if key not in actual:
                return f"{path}.{key}: missing"
            if key not in expected:
                return f"{path}.{key}: unexpected"
            if diff := mismatch(actual[key], expected[key], tolerance, f"{path}.{key}"):
                return diff
        return None
    if type(actual) is not type(expected) or actual != expected:
        return f"{path}: {actual!r} != {expected!r}"
    return None
