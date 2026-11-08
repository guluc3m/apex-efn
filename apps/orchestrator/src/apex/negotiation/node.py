"""Graph-facing adapter (D5-07b): implements DEV-4's ``NegotiationPort`` with the ADR-900 contract.

``negotiate(offer, tenant_id=..., idempotency_key=...)`` starts the negotiation on the first call and
advances it on every later call with the same key (``negotiate:<subject_ref>:<attempt>``). It returns a
:class:`NegotiationResult`; ``price_minor`` is the agreed **unit** price and is set only for ``agreed``.
Non-terminal outcomes (``awaiting_human_approval``, ``awaiting_seller``, ``in_progress``) must not be
cached by the graph's effect ledger.

The offer mapping is built by the graph. The keys read here are documented in :class:`OfferInput`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from apex.negotiation.engine import NegotiationEngine, OpenRequest
from apex.negotiation.models import NegotiationOutcome, NegotiationParams, NegotiationSession


class OfferInput(BaseModel):
    """The part of the graph's offer mapping the negotiator needs. Extra keys are ignored."""

    model_config = ConfigDict(extra="ignore")

    offer_id: str
    platform: str
    seller_id: str
    product_id: str = Field(validation_alias="platform_offer_id")
    category: str | None = None


class NegotiationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: NegotiationOutcome
    negotiation_id: str
    price_minor: int | None
    currency: str | None
    quantity: int | None
    reason: str | None = None


ParamsResolver = Callable[[OfferInput, str], Awaitable[tuple[NegotiationParams, str, str]]]
"""Returns ``(params, config_version, account_id)`` for an offer and tenant. Owned by the caller:
it reads tenant config (``neg.*``) and the buyer profile, and fails loudly on unset keys (Q7)."""


def to_result(session: NegotiationSession) -> NegotiationResult:
    agreed = session.status is NegotiationOutcome.AGREED and session.agreed is not None
    return NegotiationResult(
        outcome=session.status,
        negotiation_id=session.id,
        price_minor=session.agreed.unit_price_minor if agreed and session.agreed else None,
        currency=session.agreed.currency if agreed and session.agreed else None,
        quantity=session.params.quantity if agreed else None,
        reason=session.stop_reason,
    )


class EngineNegotiationPort:
    def __init__(self, engine: NegotiationEngine, resolve: ParamsResolver) -> None:
        self._engine = engine
        self._resolve = resolve
        self._ids: dict[str, str] = {}

    async def negotiate(
        self, offer: Mapping[str, Any], *, tenant_id: str, idempotency_key: str
    ) -> NegotiationResult:
        known = self._ids.get(idempotency_key)
        if known is not None:
            return to_result(await self._engine.advance(known))
        data = OfferInput.model_validate(dict(offer))
        params, config_version, account_id = await self._resolve(data, tenant_id)
        session = await self._engine.start(
            OpenRequest(
                tenant_id=tenant_id,
                platform=data.platform,
                seller_id=data.seller_id,
                product_id=data.product_id,
                account_id=account_id,
                config_version=config_version,
                params=params,
            ),
            idempotency_key=idempotency_key,
        )
        self._ids[idempotency_key] = session.id
        return to_result(session)
