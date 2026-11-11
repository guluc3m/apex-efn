"""Cross-platform seller identity resolution (D5-12).

The important property is the negative one: **without a configured threshold nothing merges.** A wrong merge
pools two companies' confidence, disputes and negotiation history, so the default has to be "keep them apart".
"""

from __future__ import annotations

import pytest

from apex.negotiation.seller_identity import (
    InMemoryIdentityStore,
    SellerIdentity,
    SellerIdentityResolver,
    compare,
    name_similarity,
    normalize_name,
)

A = SellerIdentity("mock-a", "a-solid-veteran", "Shenzhen Bright Gloves Co., Ltd.", "CN")
B = SellerIdentity("mock-b", "b-gloves-01", "SHENZHEN BRIGHT GLOVES CO LTD", "CN")
OTHER = SellerIdentity("mock-b", "b-other", "Guangzhou Plastics Trading", "CN")


# ----- normalisation ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Shenzhen Bright Gloves Co., Ltd.", "SHENZHEN BRIGHT GLOVES CO LTD"),
        ("Acme S.L.", "Acme SL"),
        ("Café Ñandú S.A.", "Cafe Nandu SA"),
    ],
)
def test_names_that_differ_only_in_form_normalise_the_same(left: str, right: str) -> None:
    assert normalize_name(left) == normalize_name(right)


def test_the_legal_form_is_dropped_but_the_trade_name_is_not() -> None:
    assert normalize_name("Bright Gloves GmbH") == "bright gloves"
    assert normalize_name("Gloves") == "gloves"


def test_an_empty_name_never_matches() -> None:
    assert name_similarity("", "Acme") == 0.0


# ----- comparison ---------------------------------------------------------------------------------


def test_an_identical_name_scores_one() -> None:
    assert name_similarity(A.name, B.name) == 1.0


def test_a_disagreeing_country_lowers_the_score() -> None:
    same_name_other_country = SellerIdentity("mock-b", "x", A.name, "VN")
    agree = compare(A, B, country_weight=0.2)
    disagree = compare(A, same_name_other_country, country_weight=0.2)
    assert agree.score > disagree.score
    assert disagree.country_agrees is False


def test_an_unknown_country_is_neither_agreement_nor_disagreement() -> None:
    unknown = SellerIdentity("mock-b", "x", A.name, None)
    score = compare(A, unknown, country_weight=0.2)
    assert score.country_agrees is None
    assert score.score == pytest.approx(1.0)


def test_the_explanation_names_every_component() -> None:
    text = compare(A, B, country_weight=0.2).explain()
    assert "name 1.00" in text and "country agrees: true" in text and "score 1.00" in text


# ----- resolution ---------------------------------------------------------------------------------


async def test_without_a_threshold_nothing_ever_merges() -> None:
    """The default while the rule is undecided: every platform id keeps its own identity."""
    store = InMemoryIdentityStore()
    resolver = SellerIdentityResolver(store=store, threshold=None)
    first = await resolver.resolve(A)
    second = await resolver.resolve(B)
    assert first.canonical_id != second.canonical_id
    assert first.merged is False and second.merged is False


async def test_with_a_threshold_the_same_seller_merges() -> None:
    store = InMemoryIdentityStore()
    resolver = SellerIdentityResolver(store=store, threshold=0.9, country_weight=0.2)
    first = await resolver.resolve(A)
    second = await resolver.resolve(B)
    assert second.canonical_id == first.canonical_id
    assert second.merged is True
    assert second.matched == A
    assert second.score is not None and second.score.score >= 0.9


async def test_a_different_seller_does_not_merge() -> None:
    store = InMemoryIdentityStore()
    resolver = SellerIdentityResolver(store=store, threshold=0.9)
    first = await resolver.resolve(A)
    other = await resolver.resolve(OTHER)
    assert other.canonical_id != first.canonical_id
    assert other.merged is False


async def test_resolving_the_same_platform_id_twice_is_stable() -> None:
    store = InMemoryIdentityStore()
    resolver = SellerIdentityResolver(store=store, threshold=0.9)
    first = await resolver.resolve(A)
    again = await resolver.resolve(A)
    assert again.canonical_id == first.canonical_id
    assert again.merged is False  # already known, not a new merge


async def test_a_merge_is_visible_on_the_known_side() -> None:
    store = InMemoryIdentityStore()
    resolver = SellerIdentityResolver(store=store, threshold=0.9, country_weight=0.2)
    first = await resolver.resolve(A)
    await resolver.resolve(B)
    assert await store.canonical_for("mock-b", "b-gloves-01") == first.canonical_id
    assert await store.canonical_for("mock-a", "a-solid-veteran") == first.canonical_id


async def test_the_threshold_is_inclusive() -> None:
    store = InMemoryIdentityStore()
    score = compare(A, B, country_weight=0.0).score
    resolver = SellerIdentityResolver(store=store, threshold=score)
    first = await resolver.resolve(A)
    second = await resolver.resolve(B)
    assert second.canonical_id == first.canonical_id
