"""``DomainCsvImporter``: the domain parser behind the onboarding port (ADR-305)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex.agents.csv_importer import DomainCsvImporter
from apex.agents.fx import InMemoryFxRateReader
from apex.domain.finance.csv_import import CsvImportError
from tests.agents.test_fx import NOW, TENANT, _seeded_config

FIXTURES = Path(__file__).parents[4] / "packages" / "test-vectors" / "finance"


async def test_valid_file_gives_a_json_report_with_duplicate_and_conversion_counts() -> None:
    importer = DomainCsvImporter(rates=InMemoryFxRateReader(), config=await _seeded_config())
    result = await importer.parse(
        (FIXTURES / "valid.csv").read_bytes(), base_currency="EUR", tenant_id=TENANT, now=NOW
    )
    json.dumps(result.report)  # JSON-safe: no date or model objects left
    assert result.report["rows_ok"] > 0
    assert result.report["rows_duplicated"] == 0
    assert "rows_converted" in result.report


async def test_unreadable_file_raises_csv_import_error() -> None:
    importer = DomainCsvImporter(rates=InMemoryFxRateReader(), config=await _seeded_config())
    with pytest.raises(CsvImportError):
        await importer.parse(b"\xff\xfe\x00", base_currency="EUR", tenant_id=TENANT, now=NOW)
