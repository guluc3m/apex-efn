"""Header mapping suggestion (D4-07): only headers reach the model; targets stay canonical."""

from __future__ import annotations

from typing import Any

import pytest

from apex.agents.header_mapping import HeaderMapper, MappingError, apply_mapping, unknown_headers
from apex.agents.schemas import HeaderMappingItem, HeaderMappingSuggestion
from apex.llm.prompts import PromptRegistry

CSV = b"fecha;concepto;importe\n2026-09;cash_balance;100\n"


class _Gateway:
    def __init__(self, items: list[HeaderMappingItem]) -> None:
        self.items, self.calls = items, []

    async def chat_structured(self, role: Any, messages: Any, schema: Any, **kw: Any) -> Any:
        self.calls.append(messages)
        return HeaderMappingSuggestion(mappings=self.items)


def test_unknown_headers_skip_canonical_ones() -> None:
    assert unknown_headers(b"period,metric,Importe,value_minor\n") == ["Importe"]


def test_apply_mapping_rewrites_only_the_header_row() -> None:
    out = apply_mapping(CSV, {"fecha": "period", "concepto": "metric", "importe": "value_minor"})
    assert out == b"period;metric;value_minor\n2026-09;cash_balance;100\n"


@pytest.mark.parametrize(
    "mapping",
    [{"fecha": "period", "concepto": "period"}, {"fecha": "nope"}, {"ghost": "period"}],
)
def test_apply_mapping_refuses_bad_mappings(mapping: dict[str, str]) -> None:
    with pytest.raises(MappingError):
        apply_mapping(CSV, mapping)


def test_apply_mapping_refuses_a_target_already_present() -> None:
    with pytest.raises(MappingError):
        apply_mapping(b"period,fecha\n", {"fecha": "period"})


async def test_suggestion_drops_invented_and_repeated_targets_and_never_sends_values() -> None:
    gateway = _Gateway(
        [
            HeaderMappingItem(source="fecha", target="period", reason="date"),
            HeaderMappingItem(source="concepto", target="period", reason="dup"),
            HeaderMappingItem(source="importe", target="amount", reason="invented"),
            HeaderMappingItem(source="other", target="metric", reason="not in file"),
        ]
    )
    out = await HeaderMapper(gateway, PromptRegistry()).suggest(  # type: ignore[arg-type]
        tenant_id="t", session_id="s", content=CSV
    )
    assert [(m["source"], m["target"]) for m in out["mappings"]] == [
        ("fecha", "period"),
        ("concepto", None),
        ("importe", None),
    ]
    assert "cash_balance" not in str(gateway.calls)
