"""``FinancePort`` over DEV-3's landed cost and financial fit (D3-05).

Inputs the tenant has not supplied stay unknown (ADR-900 Q5): duty and import VAT are per category/country and
the offer carries neither yet, so those lines are omitted rather than set to 0. The envelope is the category's
``BudgetEnvelope.available`` from the active snapshot; the closed CSV metric enum has no budget metric, so
today the envelope list is empty and every offer is ``out_of_budget`` (ADR-305 point 6, ADR-900 Q2).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apex.agents.onboarding import OnboardingService
from apex.agents.ports import FitOutcome
from apex.common.clock import Clock
from apex.contracts.generated.models import Currency
from apex.domain.finance.landed import (
    FinancialSnapshot,
    LandedCostError,
    LandedCostInputs,
    financial_fit,
    landed_cost,
)
from apex.tenant_config.service import TenantConfigService


class FinanceUnavailable(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class DomainFinancePort:
    config: TenantConfigService
    onboarding: OnboardingService
    clock: Clock

    async def fit(self, offer: Mapping[str, Any], *, tenant_id: str) -> FitOutcome:
        try:
            active = await self.onboarding.require_active_snapshot(tenant_id=tenant_id)
        except Exception as exc:  # OnboardingIncomplete: criterion 1 normally stops this earlier
            raise FinanceUnavailable("no_active_snapshot", str(exc)) from exc
        stale = await self.onboarding.is_financials_stale(tenant_id=tenant_id)
        effective = await self.config.effective(tenant_id, offer.get("category"))
        finance = effective.typed.finance
        derived = active.report.get("derived", {})
        category = offer.get("category")
        envelope = sum(
            int(e["available"]["amount_minor"])
            for e in derived.get("envelopes", [])
            if e.get("category") == category
        )
        capacity = int(derived.get("net_buying_capacity", {}).get("amount_minor", 0))
        try:
            breakdown = landed_cost(
                LandedCostInputs(
                    unit_price_minor=offer["unit_price_eur_minor"],
                    quantity=offer["quantity"],
                    currency=Currency.EUR,
                    shipping_minor=None,
                    insurance_minor=None,
                    fx_conversion_minor=None,
                    cost_of_capital_rate=finance.cost_of_capital_rate,
                )
            )
        except LandedCostError as exc:
            raise FinanceUnavailable(exc.code, str(exc)) from exc
        fit = financial_fit(
            offer_id=offer["offer_id"],
            breakdown=breakdown,
            snapshot=FinancialSnapshot(
                envelope_minor=envelope,
                treasury_minor=capacity,  # already net of credit line, tax reserve and buffer (ADR-305)
                safety_buffer_pct=Decimal(finance.safety_buffer_pct),
                as_of=active.activated_at,
                stale=stale,
            ),
            now=self.clock.now(),
        )
        return FitOutcome(
            verdict=fit.verdict.value,
            financials_stale=stale,
            fx_provisional=False,
            landed_cost_total_minor=breakdown.total.amount_minor,
            landed_cost=breakdown,
        )


__all__ = ["DomainFinancePort", "FinanceUnavailable"]
