"""Buyer-side simulation over the mocked marketplace (D5-11).

Several simulated buyers search the ``mock-c`` fake platform, pick a supplier, negotiate through its
threads API with the real negotiation engine and end in ``agreed``, ``escalated`` (human gate) or
``no_agreement``. Everything is local: no database, no Docker, no network beyond the mock marketplace
and the optional OpenAI-compatible stub.

Public interface:

- :func:`run_scenario` — runs the scenario and returns a JSON-serialisable :class:`ScenarioReport`.
- :mod:`apex.negotiation.sim.models` — the report and configuration models the web UI consumes.
- ``python -m apex.negotiation.sim run --marketplace-url ...`` — human-readable transcript + JSON.
"""

from __future__ import annotations

from apex.negotiation.sim.models import (
    BuyerProfile,
    BuyerRun,
    ScenarioConfig,
    ScenarioReport,
    Step,
    TranscriptLine,
)
from apex.negotiation.sim.pipeline import run_scenario

__all__ = [
    "BuyerProfile",
    "BuyerRun",
    "ScenarioConfig",
    "ScenarioReport",
    "Step",
    "TranscriptLine",
    "run_scenario",
]
