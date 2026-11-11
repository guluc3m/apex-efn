"""``CsvImporter`` over DEV-3's deterministic ``csv_import.parse`` (D3-04, ADR-305).

Rates and the stale-after window are read per call, never cached, so a fresh rate ingestion applies at once.
Envelopes are always empty by decision (ADR-900 Q2): the CSV has no budget metric.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from apex.agents.fx import FxRateReader
from apex.domain.finance.csv_import import ImportResult, parse
from apex.domain.fx import FxConfig
from apex.tenant_config.service import TenantConfigService


@dataclass(frozen=True)
class _Result:
    report: dict[str, Any]
    warning_codes: list[str]


@dataclass(frozen=True)
class DomainCsvImporter:
    rates: FxRateReader
    config: TenantConfigService

    async def parse(
        self, content: bytes, *, base_currency: str, tenant_id: str, now: datetime
    ) -> _Result:
        effective = await self.config.effective(tenant_id, None)
        cfg = FxConfig(max_age_hours=effective.typed.fx.max_age_hours)
        result: ImportResult = parse(content, base_currency, await self.rates.rates(), now, cfg)
        report = result.report.model_dump(mode="json")
        report["rows_duplicated"] = result.rows_duplicated
        report["rows_converted"] = result.rows_converted
        return _Result(report=report, warning_codes=result.warning_codes)
