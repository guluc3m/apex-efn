"""Dashboard read model over the offer, analysis and gate stores (issue #305, D4-11).

It joins what the other services already persist; it computes no price, band or score. Actions go through
``GateAgent.decide_deal_action`` so the blocking rules and the signed decision live in one place.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from apex.agents.gate import (
    Deal,
    DealAction,
    DiscardReason,
    GateAgent,
    GateRules,
    GateStore,
)
from apex.agents.missions import MissionStore
from apex.agents.offers import Offer, OfferAnalysis, OfferStore
from apex.agents.ports import DecisionRef


class Dashboard:
    def __init__(
        self,
        *,
        offers: OfferStore,
        missions: MissionStore,
        gate_store: GateStore,
        gate: GateAgent,
        rules_for: Callable[[str], GateRules],
    ) -> None:
        self._offers = offers
        self._missions = missions
        self._gate_store = gate_store
        self._gate = gate
        self._rules_for = rules_for

    async def deals(
        self,
        *,
        tenant_id: str,
        platform: str | None = None,
        price_band: str | None = None,
        verdict: str | None = None,
        signature_status: str | None = None,  # ponytail: no signature state is stored on deals yet
    ) -> list[Deal]:
        rules = self._rules_for(tenant_id)
        out: list[Deal] = []
        for mission in await self._missions.list_for_tenant(tenant_id):
            for offer in await self._offers.list_for_mission(tenant_id, mission.id):
                analysis = await self._offers.get_analysis(tenant_id, offer.id)
                if analysis is None:
                    continue  # not analysed yet: nothing honest to show
                if platform and offer.platform_id != platform:
                    continue
                if price_band and analysis.sanity.band.value != price_band:
                    continue
                if verdict and analysis.fit.verdict != verdict:
                    continue
                out.append(await self._deal(tenant_id, offer, analysis, rules))
        return out

    async def _deal(
        self, tenant_id: str, offer: Offer, analysis: OfferAnalysis, rules: GateRules
    ) -> Deal:
        item = await self._gate_store.find_for_offer(tenant_id, offer.id)
        blocked = self._gate.blocked_deal_actions(
            offer=offer,
            analysis=analysis,
            rules=rules,
            renegotiations_used=0,  # ponytail: renegotiation count is not stored yet
            gate_item=item,
        )
        names = {b.action for b in blocked}
        allowed: Sequence[str] = (
            [] if "all" in names else [a.value for a in DealAction if a.value not in names]
        )
        return Deal(
            offer=offer,
            analysis=analysis,
            gate_item_id=item.id if item else None,
            blocked_actions=blocked,
            allowed_actions=list(allowed),
        )

    async def decide(
        self,
        *,
        tenant_id: str,
        offer_id: str,
        action: DealAction,
        discard_reason: DiscardReason | None,
        comment: str | None,
        roles: Sequence[str],
    ) -> DecisionRef:
        offer = await self._offers.get(tenant_id, offer_id)
        analysis = await self._offers.get_analysis(tenant_id, offer_id)
        if offer is None or analysis is None:
            raise LookupError(f"deal {offer_id} not found")
        return await self._gate.decide_deal_action(
            tenant_id=tenant_id,
            offer=offer,
            analysis=analysis,
            action=action,
            rules=self._rules_for(tenant_id),
            renegotiations_used=0,
            gate_item=await self._gate_store.find_for_offer(tenant_id, offer_id),
            discard_reason=discard_reason,
            comment=comment,
            roles=roles,
        )
