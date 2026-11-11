"""CSV header mapping suggestion (D4-07, issue #299 item 2).

The model sees only the header row, never a data row, so no financial value enters LLM context. It only
*suggests*; code keeps targets inside the closed canonical set and the buyer confirms the mapping.
"""

from __future__ import annotations

from typing import Any

from apex.agents.schemas import HeaderMappingItem, HeaderMappingSuggestion
from apex.llm.config import LLMRole
from apex.llm.gateway import LLMGateway
from apex.llm.prompts import PromptRegistry

CANONICAL_COLUMNS = ("period", "metric", "value_minor", "value_bp", "currency", "notes")
"""Columns of the financial CSV (spec 3.1.1). Same names ``domain.finance.csv_import`` reads."""
_DELIMITERS = (",", ";", "\t")


class MappingError(ValueError):
    """The confirmed mapping is not usable (unknown header, non-canonical or repeated target)."""


def _split_header(content: bytes) -> tuple[str, str, list[str]]:
    text = content.decode("utf-8-sig", errors="replace")
    line, _, rest = text.partition("\n")
    line = line.rstrip("\r")
    delimiter = max(_DELIMITERS, key=line.count)
    return delimiter, rest, [h.strip() for h in line.split(delimiter)]


def unknown_headers(content: bytes) -> list[str]:
    _, _, headers = _split_header(content)
    return [h for h in headers if h and h.lower() not in CANONICAL_COLUMNS]


def apply_mapping(content: bytes, mapping: dict[str, str]) -> bytes:
    """Rewrite only the header row. Rows are untouched, so the importer's per-row checks still apply."""
    delimiter, rest, headers = _split_header(content)
    targets = list(mapping.values())
    if len(set(targets)) != len(targets) or any(t not in CANONICAL_COLUMNS for t in targets):
        raise MappingError("mapping targets must be distinct canonical columns")
    if any(s not in headers for s in mapping):
        raise MappingError("mapping names a header that is not in the file")
    clash = {h.lower() for h in headers if h not in mapping} & set(targets)
    if clash:
        raise MappingError(f"canonical columns already present: {sorted(clash)}")
    new = delimiter.join(mapping.get(h, h) for h in headers)
    return (new + "\n" + rest).encode()


class HeaderMapper:
    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry) -> None:
        self._gateway = gateway
        self._prompts = prompts

    async def suggest(self, *, tenant_id: str, session_id: str, content: bytes) -> dict[str, Any]:
        unknown = unknown_headers(content)
        if not unknown:
            return {"canonical_columns": list(CANONICAL_COLUMNS), "mappings": []}
        rendered = self._prompts.render(
            "extractor_csv_header_mapping",
            canonical_columns=list(CANONICAL_COLUMNS),
            unknown_headers=unknown,
        )
        draft = await self._gateway.chat_structured(
            LLMRole.EXTRACTOR,
            rendered.messages,
            HeaderMappingSuggestion,
            mission_id=f"onboarding:{session_id}",
            tenant_id=tenant_id,
            prompt_version=rendered.prompt_version,
        )
        return {
            "canonical_columns": list(CANONICAL_COLUMNS),
            "mappings": _checked(draft.mappings, unknown),
        }


def _checked(items: list[HeaderMappingItem], unknown: list[str]) -> list[dict[str, Any]]:
    """One entry per unknown header, in file order. An invalid or repeated target becomes null."""
    by_source = {i.source: i for i in items if i.source in unknown}
    used: set[str] = set()
    out: list[dict[str, Any]] = []
    for header in unknown:
        item = by_source.get(header)
        target = item.target if item else None
        if target not in CANONICAL_COLUMNS or target in used:
            target = None
        if target:
            used.add(target)
        out.append({"source": header, "target": target, "reason": item.reason if item else ""})
    return out


__all__ = ["CANONICAL_COLUMNS", "HeaderMapper", "MappingError", "apply_mapping", "unknown_headers"]
