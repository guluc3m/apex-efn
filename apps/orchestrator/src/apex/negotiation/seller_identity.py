"""Cross-platform seller identity resolution (D5-12, spec §10 phase 3).

The same seller appears on several marketplaces under different ids and slightly different names
(``Shenzhen Bright Gloves Co.`` vs ``SHENZHEN BRIGHT GLOVES CO., LTD``). The schema already models this: a
``Seller`` has one ``canonical_id`` and many ``SellerPlatformId`` rows.

**This module never decides on its own that two sellers are the same.** The spec does not define a matching
rule, and a wrong merge is worse than a missed one: it would pool two companies' confidence, disputes and
negotiation history. So:

* The comparison is **deterministic** and explainable: normalised name similarity plus country agreement,
  with every component returned so a human can see why.
* A merge happens only when a **threshold is supplied**. Without one, every platform id keeps its own
  canonical identity. The threshold belongs in tenant config (a TL decision); until it exists, nothing merges.
* A merge is never destructive: it records the alias, so a later correction can split them again.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Protocol

#: Legal-form suffixes that carry no identity: two sellers differing only in these are the same company.
LEGAL_SUFFIXES: tuple[str, ...] = (
    "sl",
    "s l",
    "sa",
    "s a",
    "srl",
    "s r l",
    "gmbh",
    "ltd",
    "limited",
    "llc",
    "inc",
    "co",
    "company",
    "corp",
    "corporation",
    "bv",
    "nv",
    "ag",
    "kg",
    "pty",
    "pte",
    "sas",
    "sarl",
    "oy",
    "ab",
    "as",
    "spa",
    "s p a",
)

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Case-fold, strip accents and punctuation, drop the legal form and collapse whitespace.

    ``"Shenzhen Bright Gloves Co., Ltd."`` and ``"SHENZHEN BRIGHT GLOVES CO LTD"`` both become
    ``"shenzhen bright gloves"``.
    """
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    # Dots join the letters of an abbreviation ("S.L." -> "SL"), so the legal form stays one token.
    folded = folded.casefold().replace(".", "")
    folded = _PUNCTUATION.sub(" ", folded)
    words = _WHITESPACE.sub(" ", folded).strip().split()
    while words and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


def name_similarity(a: str, b: str) -> float:
    """Ratio of the normalised names in ``[0, 1]``. Deterministic: same input, same number, always."""
    left, right = normalize_name(a), normalize_name(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


@dataclass(frozen=True)
class SellerIdentity:
    """One observation of a seller on one platform."""

    platform: str
    platform_seller_id: str
    name: str
    country: str | None = None


@dataclass(frozen=True)
class MatchScore:
    """Why two observations were (or were not) considered the same seller."""

    name_similarity: float
    country_agrees: bool | None
    """``None`` when either side has no country: unknown is not disagreement."""
    score: float

    def explain(self) -> str:
        country = "unknown" if self.country_agrees is None else str(self.country_agrees).lower()
        return f"name {self.name_similarity:.2f}, country agrees: {country}, score {self.score:.2f}"


def compare(a: SellerIdentity, b: SellerIdentity, *, country_weight: float) -> MatchScore:
    """Compare two observations. ``country_weight`` is how much an agreeing country adds.

    A **disagreeing** country subtracts the same weight: two companies in different countries with similar
    names are more likely different sellers than the same one.
    """
    similarity = name_similarity(a.name, b.name)
    if a.country is None or b.country is None:
        agrees: bool | None = None
        adjustment = 0.0
    else:
        agrees = a.country.upper() == b.country.upper()
        adjustment = country_weight if agrees else -country_weight
    return MatchScore(
        name_similarity=similarity,
        country_agrees=agrees,
        score=max(0.0, min(1.0, similarity + adjustment)),
    )


class IdentityStore(Protocol):
    """Alias table: ``(platform, platform_seller_id) -> canonical_id``."""

    async def canonical_for(self, platform: str, platform_seller_id: str) -> str | None: ...

    async def known(self) -> Iterable[tuple[str, SellerIdentity]]: ...

    async def link(self, canonical_id: str, identity: SellerIdentity) -> None: ...


@dataclass
class InMemoryIdentityStore:
    _by_platform_id: dict[tuple[str, str], str] = field(default_factory=dict)
    _canonical: dict[str, SellerIdentity] = field(default_factory=dict)

    async def canonical_for(self, platform: str, platform_seller_id: str) -> str | None:
        return self._by_platform_id.get((platform, platform_seller_id))

    async def known(self) -> Iterable[tuple[str, SellerIdentity]]:
        return list(self._canonical.items())

    async def link(self, canonical_id: str, identity: SellerIdentity) -> None:
        self._by_platform_id[(identity.platform, identity.platform_seller_id)] = canonical_id
        self._canonical.setdefault(canonical_id, identity)


@dataclass(frozen=True)
class Resolution:
    canonical_id: str
    merged: bool
    """True when this observation was attached to an existing seller."""
    matched: SellerIdentity | None = None
    score: MatchScore | None = None


@dataclass(frozen=True)
class SellerIdentityResolver:
    """Resolve an observation to a canonical seller id.

    ``threshold`` comes from tenant config. ``None`` means "never merge": every observation gets its own
    canonical identity, which is the correct default while the rule is undecided.
    """

    store: IdentityStore
    threshold: float | None = None
    country_weight: float = 0.0
    new_id: str = "seller"

    async def resolve(self, identity: SellerIdentity) -> Resolution:
        existing = await self.store.canonical_for(identity.platform, identity.platform_seller_id)
        if existing is not None:
            return Resolution(canonical_id=existing, merged=False)
        best: tuple[float, str, SellerIdentity, MatchScore] | None = None
        if self.threshold is not None:
            for canonical_id, known in await self.store.known():
                score = compare(identity, known, country_weight=self.country_weight)
                if score.score >= self.threshold and (best is None or score.score > best[0]):
                    best = (score.score, canonical_id, known, score)
        if best is not None:
            _, canonical_id, known, score = best
            await self.store.link(canonical_id, identity)
            return Resolution(canonical_id=canonical_id, merged=True, matched=known, score=score)
        canonical_id = self._new_canonical_id(identity)
        await self.store.link(canonical_id, identity)
        return Resolution(canonical_id=canonical_id, merged=False)

    def _new_canonical_id(self, identity: SellerIdentity) -> str:
        return f"{self.new_id}:{identity.platform}:{identity.platform_seller_id}"


__all__ = [
    "InMemoryIdentityStore",
    "IdentityStore",
    "LEGAL_SUFFIXES",
    "MatchScore",
    "Resolution",
    "SellerIdentity",
    "SellerIdentityResolver",
    "compare",
    "name_similarity",
    "normalize_name",
]
