"""``SanityPort`` over DEV-3's price sanity engine (D3-07).

The reference set is the other offers of the same mission, per unit in EUR. History and benchmark come from
the D2-13 analytics store, which is not wired into the orchestrator yet, so they stay empty: with fewer than
``sanity.min_sample`` prices the engine answers ``insufficient_reference`` and the offer goes to the gate
(ADR-900 Q12). Nothing is invented here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from apex.agents.offers import OfferStore
from apex.agents.ports import PriceBand, SanityOutcome
from apex.common.clock import Clock
from apex.domain.sanity import ReferenceSet, SanityConfig, SanityError, check
from apex.tenant_config.service import TenantConfigService


class SanityUnavailable(Exception):
    """The engine refused to run. ``code`` is DEV-3's closed error code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class DomainSanityPort:
    config: TenantConfigService
    offers: OfferStore
    clock: Clock

    async def check(
        self, offer: Mapping[str, Any], *, tenant_id: str, price_minor: int | None
    ) -> SanityOutcome:
        effective = await self.config.effective(tenant_id, offer.get("category"))
        price = price_minor if price_minor is not None else offer["unit_price_eur_minor"]
        peers = [
            o.unit_price_eur_minor
            for o in await self.offers.list_for_mission(tenant_id, offer["mission_id"])
            if o.id != offer["offer_id"]
        ]
        try:
            cfg = SanityConfig.from_mapping(
                effective.typed.sanity.model_dump(),
                f"v{effective.config_version}:{effective.content_hash[:12]}",
            )
            result = check(
                offer_id=offer["offer_id"],
                unit_price_eur_minor=price,
                reference=ReferenceSet(mission=peers),
                cfg=cfg,
                now=self.clock.now(),
            )
        except SanityError as exc:
            raise SanityUnavailable(exc.code, str(exc)) from exc
        return SanityOutcome(
            band=PriceBand(result.band.value),
            config_version=result.config_version,
            detail=result,
        )


__all__ = ["DomainSanityPort", "SanityUnavailable"]
