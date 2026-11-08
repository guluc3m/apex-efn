"""Drift guard: config/defaults/tenant-config.v1.json must match the §7 table in the spec exactly."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from apex.tenant_config.defaults import DEFAULT_PATH, load_global_layer, scope_of

REPO_ROOT = (
    Path(__file__).resolve().parents[4]
)  # tests/tenant_config → tests → orchestrator → apps → repo
SPEC = REPO_ROOT / "PROMPT-IMPLEMENTACION.md"
SCHEMA = REPO_ROOT / "config" / "defaults" / "tenant-config.schema.json"

ROW = re.compile(r"^\|\s*((?:`[^`]+`\s*,?\s*)+)\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")


def _spec_rows() -> list[tuple[str, str, str]]:
    """(key, scope, default) for every row of the §7 table. Keys like ``a``, ``b`` are split."""
    text = SPEC.read_text(encoding="utf-8")
    start = text.index("# 7. CONFIGURACIÓN POR TENANT")
    end = text.index("# 8. API", start)
    rows: list[tuple[str, str, str]] = []
    for line in text[start:end].splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        keys = re.findall(r"`([^`]+)`", m.group(1))
        for key in keys:
            rows.append((key, m.group(2).strip(), m.group(3).strip()))
    return rows


def _flatten(node: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else k))
    else:
        out[prefix] = node
    return out


def test_every_spec_key_is_in_defaults_and_vice_versa() -> None:
    spec = {k for k, _, _ in _spec_rows()}
    _, values = load_global_layer(DEFAULT_PATH)
    defaults_keys = set(_flatten(values))
    # Wildcards in the spec (seller.weights.*, llm.roles.*) are represented by their parent key.
    spec_norm = {k.replace(".*", "") for k in spec}
    assert spec_norm == defaults_keys, (
        f"missing in defaults: {sorted(spec_norm - defaults_keys)}; "
        f"extra in defaults: {sorted(defaults_keys - spec_norm)}"
    )


def test_unset_keys_match_sin_definir_in_spec() -> None:
    """Keys the spec marks 'sin definir' / 'ver ADR' must be null in the defaults file."""
    _, values = load_global_layer(DEFAULT_PATH)
    flat = _flatten(values)
    unset_in_spec = {
        k.replace(".*", "") for k, _, d in _spec_rows() if d in {"sin definir", "ver ADR"}
    }
    expected_null = set(unset_in_spec)
    actual_null = {k for k, v in flat.items() if v is None}
    assert actual_null == expected_null, (
        f"null in defaults={sorted(actual_null)}, spec={sorted(expected_null)}"
    )


def test_scalar_defaults_match_spec_values() -> None:
    """Numeric/boolean/enum defaults in the spec equal the values in the defaults file."""
    _, values = load_global_layer(DEFAULT_PATH)
    flat = _flatten(values)
    checked = 0
    for key, _scope, default in _spec_rows():
        if key.endswith(".*") or default in {"sin definir", "ver ADR"}:
            continue
        if key == "money.supported_currencies":
            assert flat[key] == ["EUR", "USD", "CNY"]
            checked += 1
            continue
        if key == "sanity.on_insufficient_reference":
            assert default == "gate" and flat[key] == "gate"
            checked += 1
            continue
        if key == "fx.pivot":
            assert flat[key] == "EUR"
            checked += 1
            continue
        if key in {"seller.min_accepted_band"}:
            assert flat[key] == default
            checked += 1
            continue
        if key == "seller.escalate_cheap_low_confidence":
            assert flat[key] is True and default == "true"
            checked += 1
            continue
        num = float(default.replace(",", "."))
        assert float(flat[key]) == num, f"{key}: defaults={flat[key]} spec={default}"
        checked += 1
    assert checked == 29  # scalar rows; sin definir / ver ADR / wildcards are checked separately


def test_scope_markers_present_for_every_key() -> None:
    scopes = scope_of(DEFAULT_PATH)
    _, values = load_global_layer(DEFAULT_PATH)
    assert set(scopes) == set(_flatten(values))


def test_defaults_file_is_valid_against_json_schema() -> None:
    import jsonschema  # type: ignore[import-untyped]

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    instance = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance, schema)
