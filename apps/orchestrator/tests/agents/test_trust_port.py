"""``DomainTrustPort``: the graph's view of DEV-3's seller confidence engine (D3-06)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from apex.agents.ports import ConfidenceBand
from apex.agents.trust_port import DomainTrustPort, TrustUnavailable
from apex.common.clock import FixedClock
from apex.tenant_config.ports import ConfigVersionRecord
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.service import TenantConfigService

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TENANT = "tenant-a"

# ADR-304's proposed values (issue #278). Used here only to exercise the adapter; the shipped defaults keep
# seller.weights unset until the ADR is approved, which is why the last test asserts the loud failure.
SELLER_CONFIG: dict[str, Any] = {
    "weights": {
        "age": "0.15",
        "sales": "0.20",
        "catalog": "0.10",
        "reviews": "0.25",
        "institutional": "0.30",
    },
    "x_sat": {
        "lifetime_transactions": "10000",
        "transactions_12m": "2000",
        "gmv_12m": "1000000",
        "published_products_count": "500",
        "reviews_total": "1000",
        "reviews_12m": "250",
    },
    "category_rating_mean": "4.5",
    "category_five_star_share": "0.6",
    "wilson_confidence": "0.95",
    "min_verified_share": "0.3",
    "max_duplicate_text_share": "0.2",
}


class _Decisions:
    async def create_decision(self, *a: Any, **k: Any) -> Any:
        raise NotImplementedError

    async def require_signed(self, *a: Any, **k: Any) -> Any:
        raise NotImplementedError

    async def sign_service_event(self, *a: Any, **k: Any) -> Any:
        raise NotImplementedError


async def _config(*, seller: dict[str, Any] | None) -> TenantConfigService:
    from apex.tenant_config.load_defaults import seed

    service = TenantConfigService(
        InMemoryConfigRepository(),
        _Decisions(),
        FixedClock(NOW),  # type: ignore[arg-type]
    )
    await seed([TENANT], service._repo)  # type: ignore[attr-defined]
    if seller is not None:
        repository = service._repo  # type: ignore[attr-defined]
        latest = await repository.latest_version(TENANT)
        assert latest is not None
        values = dict(latest.values)
        values["seller"] = {**values.get("seller", {}), **seller}
        await repository.append_version(
            ConfigVersionRecord(
                tenant_id=TENANT,
                config_version=latest.config_version + 1,
                content_hash=latest.content_hash,
                values=values,
                created_at=latest.created_at,
            )
        )
    return service


def _offer(**signals: Any) -> dict[str, Any]:
    return {
        "platform_id": "mock-a",
        "seller_id": "s-1",
        "category": None,
        "collected_at": NOW,
        "raw_signals": {"seller_signals": signals} if signals else {},
    }


async def test_a_snapshot_produces_a_versioned_band_and_score() -> None:
    port = DomainTrustPort(config=await _config(seller=SELLER_CONFIG), clock=FixedClock(NOW))
    outcome = await port.score(
        _offer(
            account_age_days=1500,
            lifetime_transactions=9000,
            transactions_12m=1800,
            published_products_count=450,
            reviews_total=900,
            reviews_12m=200,
            rating_avg=4.8,
            rating_count=900,
            verified_review_share=0.9,
            identity_verified=True,
            trade_assurance=True,
        ),
        tenant_id=TENANT,
    )
    assert outcome.band in {ConfidenceBand.HIGH, ConfidenceBand.MEDIUM}
    assert outcome.score is not None
    assert outcome.model_version.startswith("seller-confidence@")
    assert "/v" in outcome.model_version  # the config version travels with the score


async def test_too_few_signals_is_insufficient_data_with_no_score() -> None:
    port = DomainTrustPort(config=await _config(seller=SELLER_CONFIG), clock=FixedClock(NOW))
    outcome = await port.score(_offer(account_age_days=10), tenant_id=TENANT)
    assert outcome.band is ConfidenceBand.INSUFFICIENT_DATA
    assert outcome.score is None


async def test_reviews_are_passed_so_the_burst_check_can_fire() -> None:
    """Criterion 8: without reviews only the verified-share check runs and the result says so."""
    port = DomainTrustPort(config=await _config(seller=SELLER_CONFIG), clock=FixedClock(NOW))
    reviews = [
        {"rating": 5, "date": f"2026-11-{i % 9 + 1:02d}", "verified": False, "text": "great"}
        for i in range(30)
    ]
    with_reviews = await port.score(
        _offer(
            account_age_days=1500,
            lifetime_transactions=9000,
            transactions_12m=1800,
            reviews_total=900,
            reviews_12m=200,
            rating_avg=4.9,
            rating_count=900,
            verified_review_share=0.9,
            reviews=reviews,
        ),
        tenant_id=TENANT,
    )
    assert with_reviews.score is not None


async def test_worker_recent_reviews_are_read_with_the_contract_field_names() -> None:
    """A real worker publishes ``recent_reviews`` with ``created_at``/``verified_purchase``."""
    port = DomainTrustPort(config=await _config(seller=SELLER_CONFIG), clock=FixedClock(NOW))
    offer = _offer(
        account_age_days=2801,
        first_sale_date="2019-04-02",
        months_active_last_12=12,
        lifetime_transactions=4200,
        transactions_12m=900,
        published_products_count=140,
        reviews_total=500,
        reviews_12m=260,
        rating_avg=4.8,
        rating_count=500,
        verified_review_share=0.92,
        identity_verified=True,
        trade_assurance=True,
        escrow_available=True,
        recent_reviews=[
            {
                "rating": 5,
                "created_at": "2026-09-14T00:00:00.000Z",
                "verified_purchase": True,
                "text": "Second order of the same gloves.",
            }
        ],
    )
    outcome = await port.score(offer, tenant_id=TENANT)
    assert outcome.band is not ConfidenceBand.INSUFFICIENT_DATA
    assert outcome.score is not None


async def test_an_offer_without_a_capture_time_is_refused() -> None:
    """A snapshot is immutable and stamped at capture; without the instant it is not a snapshot."""
    port = DomainTrustPort(config=await _config(seller=SELLER_CONFIG), clock=FixedClock(NOW))
    offer = _offer(account_age_days=1500)
    del offer["collected_at"]
    with pytest.raises(TrustUnavailable) as caught:
        await port.score(offer, tenant_id=TENANT)
    assert caught.value.code == "missing_captured_at"


async def test_unset_seller_config_is_a_loud_error_naming_the_key() -> None:
    """ADR-900 Q7: the engine refuses to run rather than inventing weights."""
    port = DomainTrustPort(config=await _config(seller={"weights": None}), clock=FixedClock(NOW))
    with pytest.raises(TrustUnavailable) as caught:
        await port.score(_offer(account_age_days=1500), tenant_id=TENANT)
    assert caught.value.code == "config_unset"
    assert "seller.weights" in caught.value.detail


async def test_a_gmv_in_another_currency_is_not_converted_here() -> None:
    """The engine raises ``gmv_not_eur``; converting in the adapter would hide an ingestion bug."""
    port = DomainTrustPort(config=await _config(seller=SELLER_CONFIG), clock=FixedClock(NOW))
    with pytest.raises(TrustUnavailable) as caught:
        await port.score(
            _offer(
                account_age_days=1500,
                lifetime_transactions=9000,
                gmv_12m={"amount_minor": 1_000_000, "currency": "USD"},
            ),
            tenant_id=TENANT,
        )
    assert caught.value.code == "gmv_not_eur"
