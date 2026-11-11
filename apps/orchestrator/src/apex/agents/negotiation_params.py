"""Resolve the negotiation engine's parameters from tenant config (D5-07b, ADR-900 Q7).

DEV-5's ``EngineNegotiationPort`` takes a ``ParamsResolver`` and documents it as the caller's job: "it reads
tenant config (``neg.*``) and the buyer profile, and fails loudly on unset keys". This module is that
resolver, and it is deliberately strict:

* Every limit comes from the tenant's **effective** config. Nothing is defaulted here — an unset
  ``neg.target_discount`` or ``neg.max_discount`` raises, because ADR-900 Q7 says a mission cannot launch
  while a value it needs is unset.
* The discount fractions are converted to basis points with DEV-5's ``fraction_to_bp``, which rounds **down**,
  so the guardrail is never looser than the configured limit.
* The reference price is the offer's listed unit price in EUR (offers are converted at ingestion, D4-09).
* The platform account is an opaque id from a port: the orchestrator never sees credentials (D5-02).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apex.agents.offers import OfferStore
from apex.db.models.generated import ConnectedAccount, ConnectedAccountStatus
from apex.negotiation.guardrails import Counterpart, fraction_to_bp
from apex.negotiation.models import NegotiationContext, NegotiationParams
from apex.negotiation.node import OfferInput
from apex.platform.flags import FlagProvider
from apex.tenant_config.service import TenantConfigService

ParamsResolver = Callable[[OfferInput, str], Awaitable[tuple[NegotiationParams, str, str]]]

AUTONOMOUS_SEND_FLAG = "negotiation.autonomous_send"
"""D5-11: when on, the engine sends its drafts without waiting for a human. Off in Phase 1."""


class AccountResolver(Protocol):
    """``(tenant_id, platform) -> account_id``. The id is opaque; credentials stay in the worker (D5-02)."""

    async def account_for(self, *, tenant_id: str, platform: str) -> str: ...


class UnwiredAccountResolver:
    """No account registry is wired: a negotiation cannot start without an account, so this fails loudly."""

    async def account_for(self, *, tenant_id: str, platform: str) -> str:
        raise NotImplementedError("no account resolver is wired; a negotiation cannot start")


class NegotiationNotConfigured(Exception):
    """The tenant's config cannot produce a negotiation. The message names the key that is missing."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class DbAccountResolver:
    """The tenant's active ``ConnectedAccount`` for a platform (issue #370).

    Returns the row id, which is the worker's opaque ``account_id``. Credentials stay behind the vault
    ``CredentialRef`` and never pass through here.
    """

    def __init__(self, session_scope: Callable[[str], AbstractAsyncContextManager[AsyncSession]]):
        self._scope = session_scope

    async def account_for(self, *, tenant_id: str, platform: str) -> str:
        async with self._scope(tenant_id) as session:
            found = await session.scalar(
                select(ConnectedAccount.id)
                .where(ConnectedAccount.tenant_id == tenant_id)
                .where(ConnectedAccount.platform == platform)
                .where(ConnectedAccount.status == ConnectedAccountStatus.ACTIVE)
                .order_by(ConnectedAccount.id)
                .limit(1)
            )
        if found is None:
            raise NegotiationNotConfigured(f"no active connected account for platform {platform}")
        return str(found)


@dataclass(frozen=True)
class NegotiationParamsResolver:
    """``ParamsResolver`` over the tenant config, the offer store and the account port."""

    config: TenantConfigService
    offers: OfferStore
    accounts: AccountResolver
    flags: FlagProvider | None = None
    """Feature flags. ``negotiation.autonomous_send`` turns off the human approval step (D5-11). Phase 1
    keeps it off: every drafted message waits for a person (spec §3.6 step 5)."""

    def _autonomous_send_enabled(self, tenant_id: str) -> bool:
        """The flag is per tenant and defaults to off; without it every draft waits for a human."""
        if self.flags is None:
            return False
        return bool(self.flags.is_enabled(AUTONOMOUS_SEND_FLAG, {"tenant_id": tenant_id}))

    async def __call__(
        self, offer: OfferInput, tenant_id: str
    ) -> tuple[NegotiationParams, str, str]:
        offer_row = await self.offers.get(tenant_id, offer.offer_id)
        if offer_row is None:
            raise NegotiationNotConfigured(
                f"offer {offer.offer_id} is not stored for tenant {tenant_id}"
            )
        effective = await self.config.effective(tenant_id, offer.category)
        typed = effective.typed
        neg = typed.neg
        if neg.target_discount is None or neg.max_discount is None:
            raise NegotiationNotConfigured(
                "neg.target_discount and neg.max_discount must be set for this tenant before negotiating "
                "(ADR-900 Q7: they stay unset in /config/defaults)"
            )
        try:
            target_bp = fraction_to_bp(neg.target_discount)
            max_bp = fraction_to_bp(neg.max_discount)
        except ValueError as exc:
            raise NegotiationNotConfigured(
                f"neg discount is not a fraction in [0, 1): {exc}"
            ) from exc
        if target_bp > max_bp:
            raise NegotiationNotConfigured(
                f"neg.target_discount ({target_bp} bp) exceeds neg.max_discount ({max_bp} bp)"
            )
        account_id = await self.accounts.account_for(tenant_id=tenant_id, platform=offer.platform)
        params = NegotiationParams(
            currency=offer_row.currency,
            reference_price_minor=offer_row.unit_price_eur_minor,
            quantity=offer_row.quantity,
            target_discount_bp=target_bp,
            max_discount_bp=max_bp,
            max_rounds=neg.max_rounds,
            max_tokens=neg.max_tokens_per_conversation,
            max_messages_per_hour=neg.max_messages_per_hour_per_account,
            max_message_chars=neg.max_message_chars,
            allowed_counterparts=frozenset(Counterpart(c.value) for c in neg.allowed_counterparts),
            supported_currencies=frozenset(typed.money.supported_currencies),
            semi_automatic=not self._autonomous_send_enabled(tenant_id),
            context=NegotiationContext(
                product_title=str(offer_row.raw_signals.get("title") or offer_row.product_id),
                destination=offer_row.raw_signals.get("destination_country"),
                recurring=bool(offer_row.raw_signals.get("recurring", False)),
            ),
        )
        return params, f"v{effective.config_version}:{effective.content_hash[:12]}", account_id


__all__ = [
    "AccountResolver",
    "DbAccountResolver",
    "NegotiationNotConfigured",
    "NegotiationParamsResolver",
    "ParamsResolver",
    "UnwiredAccountResolver",
]
