"""``TrustPort`` over DEV-3's seller confidence engine (D3-06).

The engine is deterministic and versioned: it reads one immutable ``SellerSignalSnapshot`` plus the
``seller.*`` config slice and returns a ``SellerConfidence``. It never calls an LLM, and this adapter never
second-guesses it — it maps the engine's output onto the graph's ``TrustOutcome`` and nothing more.

Two rules from issue #278 that this adapter enforces:

* ``gmv_12m`` must already be in EUR. The engine raises ``gmv_not_eur`` otherwise, and the adapter lets that
  through: converting here would hide a bug at ingestion.
* Reviews are optional but their absence is **visible**: without them the engine only runs the
  ``low_verified_share`` check and the result carries the ``reviews_unavailable`` penalty. The adapter passes
  whatever the offer carries so criterion 8 (review burst) can fire in a mission.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from apex.agents.ports import ConfidenceBand, TrustOutcome
from apex.common.clock import Clock
from apex.contracts.generated.models import SellerSignalSnapshot
from apex.domain.trust import Review, TrustConfig, TrustError, compute
from apex.tenant_config.service import TenantConfigService

SIGNAL_KEYS: tuple[str, ...] = tuple(
    name
    for name in SellerSignalSnapshot.model_fields
    if name not in {"id", "seller_id", "captured_at", "data_completeness"}
)


class TrustUnavailable(Exception):
    """The engine refused to run. ``code`` is DEV-3's closed ``TrustErrorCode``."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class DomainTrustPort:
    """``TrustPort``: one immutable snapshot in, one versioned confidence out."""

    config: TenantConfigService
    clock: Clock

    async def score(self, offer: Mapping[str, Any], *, tenant_id: str) -> TrustOutcome:
        snapshot = _snapshot(offer)
        effective = await self.config.effective(tenant_id, offer.get("category"))
        try:
            cfg = TrustConfig.from_mapping(
                _seller_slice(effective.typed.seller),
                f"v{effective.config_version}:{effective.content_hash[:12]}",
            )
            confidence = compute(
                snapshot,
                cfg,
                now=self.clock.now(),
                reviews=_reviews(offer),
            )
        except TrustError as exc:
            raise TrustUnavailable(exc.code, str(exc)) from exc
        return TrustOutcome(
            band=ConfidenceBand(confidence.band.value),
            score=confidence.score,
            model_version=confidence.model_version,
            detail=confidence,
        )


def _snapshot(offer: Mapping[str, Any]) -> SellerSignalSnapshot:
    """The offer's raw signals are the snapshot. Missing signals stay ``None``: the engine decides."""
    raw = offer.get("raw_signals") or {}
    signals = raw.get("seller_signals") if isinstance(raw, Mapping) else None
    payload: dict[str, Any] = {
        "id": str(
            raw.get("snapshot_id")
            or f"{offer.get('platform_id', 'unknown')}:{offer.get('seller_id', 'unknown')}"
        ),
        "seller_id": str(offer.get("seller_id", "")),
        # The snapshot is immutable and stamped at capture: the offer's collection time is that instant.
        "captured_at": offer.get("collected_at") or offer.get("captured_at"),
    }
    present = 0
    if isinstance(signals, Mapping):
        for key, value in signals.items():
            if key in SellerSignalSnapshot.model_fields:
                payload[key] = value
                if value is not None:
                    present += 1
    # ``data_completeness`` is how much of the signal set the adapter actually saw, not a judgement.
    payload["data_completeness"] = min(1.0, present / len(SIGNAL_KEYS))
    if payload.get("captured_at") is None:
        raise TrustUnavailable(
            "missing_captured_at",
            f"offer {offer.get('id', '?')} has no collected_at: a snapshot must be stamped at capture",
        )
    return SellerSignalSnapshot.model_validate(payload)


def _reviews(offer: Mapping[str, Any]) -> Sequence[Review] | None:
    """The reviews the engine's structural checks need, from either shape the pipeline produces.

    ``raw_signals["reviews"]`` is the orchestrator's own shape. A real worker hands the platform's listing
    under ``seller_signals.recent_reviews`` with the contract's field names (``created_at``,
    ``verified_purchase``), so both are read here. A review without a rating or a date is not a review and is
    dropped instead of being defaulted.
    """
    raw = offer.get("raw_signals") or {}
    items = raw.get("reviews") if isinstance(raw, Mapping) else None
    if not items:
        signals = raw.get("seller_signals") if isinstance(raw, Mapping) else None
        items = signals.get("recent_reviews") if isinstance(signals, Mapping) else None
    if not items:
        return None
    reviews: list[Review] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        rating = item.get("rating")
        day = item.get("date") or item.get("created_at")
        if rating is None or day is None:
            continue
        try:
            seen = date.fromisoformat(str(day)[:10])
        except ValueError:
            continue
        reviews.append(
            Review(
                rating=int(rating),
                date=seen,
                verified=bool(item.get("verified", item.get("verified_purchase", False))),
                text=str(item.get("text") or ""),
            )
        )
    return reviews or None


def _seller_slice(section: Any) -> Mapping[str, Any]:
    """The config section as the plain mapping ``TrustConfig.from_mapping`` expects.

    Unset keys stay ``None`` so the engine raises ``config_unset`` naming the key, which is the behaviour
    ADR-900 Q7 asks for: no default is invented here.
    """
    dumped: dict[str, Any] = section.model_dump()
    return dumped


__all__ = ["DomainTrustPort", "TrustUnavailable"]
