"""Buyer-side simulation over the mocked marketplace (D5-11).

The models in this module are the public interface of the simulation: another agent builds a web UI
against the JSON they produce. Every model is pydantic and JSON-serialisable with
``model_dump(mode="json")``.

Nothing here is tenant configuration. The buyer profiles are **scenario inputs**, like the fixtures of a
test, and the conversation limits in :class:`SimLimits` exist only because ``NegotiationParams`` requires
them; the simulation never reads tenant config (there is no database). The only business numbers the
simulation uses are the buyer's own ``target_discount_bp`` / ``max_discount_bp`` and the marketplace's
listed unit price.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "BP_DENOMINATOR",
    "CURRENCIES",
    "BuyerProfile",
    "BuyerRun",
    "ChosenOffer",
    "Currency",
    "ItemReport",
    "Money",
    "ScenarioConfig",
    "ScenarioReport",
    "SellerReport",
    "SimLimits",
    "Step",
    "StepKind",
    "TranscriptLine",
    "default_buyers",
    "money",
]

BP_DENOMINATOR = 10_000

Currency = Literal["EUR", "USD", "CNY"]
CURRENCIES: frozenset[str] = frozenset({"EUR", "USD", "CNY"})
"""Closed currency enum of the contract (spec section 6)."""

StepKind = Literal[
    "search", "pick", "open", "message", "agreed", "escalated", "no_agreement", "error"
]


def money(amount_minor: int, currency: str) -> Money:
    """Money in integer minor units. Raises on a currency outside the contract's closed enum."""
    if currency not in CURRENCIES:
        raise ValueError(
            f"unsupported currency {currency!r}: the simulation only yields EUR, USD, CNY"
        )
    return Money(amount_minor=amount_minor, currency=currency)  # type: ignore[arg-type]


class Money(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    amount_minor: int
    currency: Currency


class BuyerProfile(BaseModel):
    """One simulated buyer: its volume, currency and bargaining position.

    ``target_discount_bp`` is the deepest discount the buyer is happy with; ``max_discount_bp`` is the
    first offer the playbook may make. Both are scenario inputs (fixture values), never defaults invented
    by the code.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    currency: Currency
    target_discount_bp: int = Field(ge=0, lt=BP_DENOMINATOR)
    max_discount_bp: int = Field(ge=0, lt=BP_DENOMINATOR)
    account_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_discounts(self) -> BuyerProfile:
        if self.target_discount_bp > self.max_discount_bp:
            raise ValueError("target_discount_bp must not exceed max_discount_bp")
        return self


class SimLimits(BaseModel):
    """Conversation limits handed to the engine.

    They are simulation inputs, not production tenant config: this package runs without a database and
    without the tenant-config service. Keep them explicit so a scenario can change them instead of the
    code inventing a value.
    """

    model_config = ConfigDict(extra="forbid")

    max_rounds: int = Field(default=6, ge=2)
    max_tokens: int = Field(default=20_000, gt=0)
    max_messages_per_hour: int = Field(default=30, gt=0)
    max_message_chars: int = Field(default=1_200, gt=0)
    language: Literal["en", "es"] = "en"


DEFAULT_QUANTITY = 5_000
"""Default volume for the demo buyer profiles (scenario fixture, not a business limit)."""

DEFAULT_SEARCH_QUERY = "nitrile gloves"
"""What the simulated buyers search for on the mock marketplace unless the scenario says otherwise."""


def default_buyers(quantity: int = DEFAULT_QUANTITY) -> list[BuyerProfile]:
    """Three buyers with different budgets.

    Scenario fixture data. They are intentionally different so the demo exercises the three paths:
    a EUR buyer lands on an evasive supplier (no agreement), a patient CNY buyer reaches an agreement and
    an aggressive CNY buyer escalates to the human gate.
    """
    return [
        BuyerProfile(
            id="buyer-eur-1",
            name="Delta Clinic Group",
            quantity=quantity,
            currency="EUR",
            target_discount_bp=800,
            max_discount_bp=1_500,
            account_id="acct-sim-eur-1",
        ),
        BuyerProfile(
            id="buyer-cny-1",
            name="Harbour Medical Imports",
            quantity=quantity,
            currency="CNY",
            target_discount_bp=500,
            max_discount_bp=900,
            account_id="acct-sim-cny-1",
        ),
        BuyerProfile(
            id="buyer-cny-2",
            name="Pearl River Supplies",
            quantity=quantity,
            currency="CNY",
            target_discount_bp=1_200,
            max_discount_bp=1_800,
            account_id="acct-sim-cny-2",
        ),
    ]


class ScenarioConfig(BaseModel):
    """Everything ``run_scenario`` needs. Explicit inputs only."""

    model_config = ConfigDict(extra="forbid")

    marketplace_url: str = Field(min_length=1)
    llm_url: str | None = None
    llm_api_key: str | None = Field(default=None, repr=False, exclude=True)
    """Bearer token for the provider. Hidden from ``repr`` and serialisation: it must never be logged."""
    llm_model: str | None = None
    quantity: int = Field(default=DEFAULT_QUANTITY, gt=0)
    buyers: list[BuyerProfile] = Field(default_factory=list)
    """Buyer profiles. Empty means the three :func:`default_buyers` for ``quantity``."""
    search_query: str = Field(default=DEFAULT_SEARCH_QUERY, min_length=1)
    tenant_id: str = Field(default="sim-tenant", min_length=1)
    limits: SimLimits = Field(default_factory=SimLimits)

    @model_validator(mode="after")
    def _check(self) -> ScenarioConfig:
        if not self.buyers:
            self.buyers = default_buyers(self.quantity)
        ids = [b.id for b in self.buyers]
        accounts = [b.account_id for b in self.buyers]
        if len(set(ids)) != len(ids):
            raise ValueError("buyer ids must be unique")
        if len(set(accounts)) != len(accounts):
            raise ValueError("buyer account ids must be unique (one account per buyer)")
        return self


class Step(BaseModel):
    """One phase of a buyer run, for the progress view."""

    model_config = ConfigDict(extra="forbid")

    kind: StepKind
    at: datetime
    detail: str
    price: Money | None = None


class TranscriptLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    role: Literal["buyer", "seller"]
    text: str
    at: datetime


class ChosenOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    supplier_id: str
    supplier_name: str | None
    asking_price: Money


class BuyerRun(BaseModel):
    """One simulated buyer from search to outcome.

    ``chosen`` is a plain dict (``item_id``, ``supplier_id``, ``supplier_name``, ``asking_price``) so the
    JSON the web UI consumes matches the contract literally.
    """

    model_config = ConfigDict(extra="forbid")

    buyer_id: str
    name: str
    chosen: dict[str, Any] | None = None
    steps: list[Step] = Field(default_factory=list)
    transcript: list[TranscriptLine] = Field(default_factory=list)
    outcome: str
    final_price: Money | None = None
    reason: str | None = None


class ItemReport(BaseModel):
    """An offer the simulation found. Serialises to the documented ``items`` dict."""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    title: str
    supplier_id: str
    supplier_name: str | None
    unit_price: Money
    moq: int


class SellerReport(BaseModel):
    """A supplier seen during the simulation. ``persona`` is the mock's internal label when exposed."""

    model_config = ConfigDict(extra="forbid")

    supplier_id: str
    name: str
    rating_avg: float | None
    orders_total: int | None
    persona: str | None


class ScenarioReport(BaseModel):
    """Result of one full simulation run.

    ``items`` and ``sellers`` are plain dict lists with the documented keys, so a JS consumer and a
    Python consumer see exactly the same shape.
    """

    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    finished_at: datetime
    marketplace_url: str
    llm_url: str | None
    items: list[dict[str, Any]] = Field(default_factory=list)
    sellers: list[dict[str, Any]] = Field(default_factory=list)
    buyers: list[BuyerRun] = Field(default_factory=list)
