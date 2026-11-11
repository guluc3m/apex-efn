"""Sanity re-check for the simulation (D5-11).

The real price-sanity engine is DEV-3's ``apex.domain.sanity.check`` (spec 3.3): it needs a reference
universe (mission offers, price history, category benchmark), versioned config and the DEV-3 test
vectors, none of which exist in a database-free simulation. Building a second, fake threshold set here
would invent business numbers, so the simulation uses the neutral stand-in below.

``NORMAL`` is the right answer for the mocked marketplace by construction: its sellers concede towards a
floor derived from the listed price, not to an anomalous one. The adversarial personas (``lowball`` and
friends) are exercised by the D5-09 suite, which wires the real DEV-3 engine.
"""

from __future__ import annotations

from apex.negotiation.models import NegotiationSession, Quote, SanityBand

__all__ = ["NormalSanity"]


class NormalSanity:
    """Always ``NORMAL``: no thresholds, no reference universe, no invented bands."""

    async def check(self, quote: Quote, *, session: NegotiationSession) -> SanityBand:
        return SanityBand.NORMAL
