"""End-to-end tests for the buyer-side marketplace simulation (D5-11).

No network, no Docker, no Node: a fake marketplace client and the real negotiation engine (with the
null LLM gateway, so drafts come from the deterministic templates) drive ``run_scenario`` end to end.
One scripted seller agrees, the other one holds above the buyer's target and sends the deal to the gate.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from apex.common.clock import FixedClock
from apex.negotiation.sim import BuyerProfile, ScenarioConfig, run_scenario
from apex.negotiation.sim.cli import build_parser, main
from apex.negotiation.sim.market import (
    MarketItem,
    MarketplaceUnavailable,
    SupplierMetrics,
    ThreadMessage,
)
from tests.negotiation.fakes import cooperative_seller

NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
SellerTurn = Callable[[str, int], str | None]


@dataclass
class _Thread:
    item_id: str
    messages: list[ThreadMessage] = field(default_factory=list)


class FakeMarketplace:
    """In-process ``mock-c``: one thread per item, scripted seller turns, no HTTP."""

    def __init__(
        self,
        items: list[MarketItem],
        turns: dict[str, SellerTurn],
        *,
        ratings: dict[str, float | None] | None = None,
    ) -> None:
        self._items = {item.item_id: item for item in items}
        self._turns = turns
        self._ratings = ratings or {}
        self._threads: dict[str, _Thread] = {}
        self._thread_by_item: dict[str, str] = {}
        self.closed = False
        self.healthy = True

    async def health(self) -> None:
        if not self.healthy:
            raise MarketplaceUnavailable("fake marketplace is down")

    async def search(self, query: str, *, limit: int = 20) -> list[MarketItem]:
        return list(self._items.values())

    async def item(self, item_id: str) -> MarketItem:
        return self._items[item_id]

    async def metrics(self, supplier_id: str) -> SupplierMetrics:
        return SupplierMetrics(
            supplier_id=supplier_id,
            name=supplier_id,
            rating_avg=self._ratings.get(supplier_id),
            orders_total=100,
        )

    async def open_thread(self, item_id: str) -> str:
        thread_id = self._thread_by_item.get(item_id)
        if thread_id is None:
            thread_id = f"thread-{item_id}"
            self._thread_by_item[item_id] = thread_id
            self._threads[thread_id] = _Thread(item_id=item_id)
        return thread_id

    async def send(self, thread_id: str, body: str) -> None:
        thread = self._threads[thread_id]
        thread.messages.append(
            ThreadMessage(seq=len(thread.messages) + 1, author="buyer", body=body, sent_at=NOW)
        )
        turn = self._turns[thread.item_id]
        reply = turn(body, sum(1 for message in thread.messages if message.author == "buyer"))
        if reply is not None:
            thread.messages.append(
                ThreadMessage(
                    seq=len(thread.messages) + 1, author="supplier", body=reply, sent_at=NOW
                )
            )

    async def messages(self, thread_id: str, *, after_seq: int = 0) -> list[ThreadMessage]:
        return [message for message in self._threads[thread_id].messages if message.seq > after_seq]

    async def aclose(self) -> None:
        self.closed = True


def holds_at(price_minor: int, currency: str) -> SellerTurn:
    """A seller that never moves: its one quote stays above the buyer's target."""

    def turn(agent: str, n: int) -> str | None:
        return f"Sorry, our best price is {currency} {price_minor / 100:.2f} per unit."

    return turn


def scenario_config() -> ScenarioConfig:
    return ScenarioConfig(
        marketplace_url="http://fake-market",
        quantity=5_000,
        buyers=[
            BuyerProfile(
                id="eur-buyer",
                name="Euro Buyer",
                quantity=5_000,
                currency="EUR",
                target_discount_bp=800,
                max_discount_bp=1_500,
                account_id="acct-eur",
            ),
            BuyerProfile(
                id="cny-buyer",
                name="CNY Buyer",
                quantity=5_000,
                currency="CNY",
                target_discount_bp=1_200,
                max_discount_bp=1_800,
                account_id="acct-cny",
            ),
        ],
    )


def fake_marketplace() -> FakeMarketplace:
    items = [
        MarketItem(
            item_id="fake-eur",
            title="Nitrile Gloves M (fake)",
            supplier_id="s-eur",
            supplier_name="Fake EUR Supplier",
            unit_price_minor=465,
            currency="EUR",
            min_order=300,
        ),
        MarketItem(
            item_id="fake-cny",
            title="Nitrile Gloves M (fake, CNY)",
            supplier_id="s-cny",
            supplier_name="Fake CNY Supplier",
            unit_price_minor=3_080,
            currency="CNY",
            min_order=500,
        ),
    ]
    return FakeMarketplace(
        items,
        {"fake-eur": cooperative_seller(), "fake-cny": holds_at(2_865, "CNY")},
        ratings={"s-eur": 4.8, "s-cny": 4.4},
    )


async def test_one_buyer_agrees_and_another_escalates_to_the_gate() -> None:
    market = fake_marketplace()
    report = await run_scenario(scenario_config(), client=market, clock=FixedClock(NOW))

    assert [run.buyer_id for run in report.buyers] == ["eur-buyer", "cny-buyer"]
    agreed, escalated = report.buyers

    assert agreed.outcome == "agreed"
    assert agreed.chosen is not None
    assert agreed.chosen["item_id"] == "fake-eur"
    assert agreed.chosen["asking_price"] == {"amount_minor": 465, "currency": "EUR"}
    assert agreed.final_price is not None and agreed.final_price.currency == "EUR"
    assert agreed.final_price.amount_minor <= 428  # the buyer's 8% target
    assert agreed.reason == "seller_confirmed_in_writing"

    assert escalated.outcome == "escalated"
    assert escalated.chosen is not None
    assert escalated.chosen["item_id"] == "fake-cny"
    assert escalated.final_price is not None
    assert escalated.final_price.amount_minor == 2_865  # the quote the gate must judge
    assert escalated.reason == "best_quote_above_target"

    # Distinct buyers used distinct accounts and did not share a negotiation.
    assert agreed.chosen["supplier_id"] != escalated.chosen["supplier_id"]
    assert agreed.steps[0].kind == "search"
    assert agreed.steps[1].kind == "pick"
    assert any(step.kind == "open" for step in agreed.steps)
    assert agreed.steps[-1].kind == "agreed"
    assert escalated.steps[-1].kind == "escalated"


async def test_steps_record_the_offer_ladder_and_the_transcript_both_sides() -> None:
    report = await run_scenario(scenario_config(), client=fake_marketplace(), clock=FixedClock(NOW))
    agreed = report.buyers[0]

    offers = [step for step in agreed.steps if step.kind == "message"]
    assert offers, "the buyer sent messages"
    assert offers[0].price is None, "the opening message asks for tiers and states no price"
    prices = [step.price.amount_minor for step in offers if step.price is not None]
    assert len(prices) >= 2
    assert prices == sorted(prices), "the ladder only moves up"

    roles = {line.role for line in agreed.transcript}
    assert roles == {"buyer", "seller"}
    assert [line.seq for line in agreed.transcript] == sorted(
        line.seq for line in agreed.transcript
    )
    assert any("Summary" in line.text for line in agreed.transcript if line.role == "buyer")


async def test_report_is_json_serialisable_and_carries_items_and_sellers() -> None:
    report = await run_scenario(scenario_config(), client=fake_marketplace(), clock=FixedClock(NOW))
    payload = report.model_dump(mode="json")
    encoded = json.dumps(payload)  # must not raise

    assert json.loads(encoded)["marketplace_url"] == "http://fake-market"
    assert {item["item_id"] for item in payload["items"]} == {"fake-eur", "fake-cny"}
    eur_item = next(item for item in payload["items"] if item["item_id"] == "fake-eur")
    assert eur_item["unit_price"] == {"amount_minor": 465, "currency": "EUR"}
    assert eur_item["moq"] == 300
    assert {seller["supplier_id"] for seller in payload["sellers"]} == {"s-eur", "s-cny"}
    seller = next(entry for entry in payload["sellers"] if entry["supplier_id"] == "s-eur")
    assert seller["rating_avg"] == 4.8
    assert seller["orders_total"] == 100
    assert seller["persona"] is None
    assert len(payload["buyers"]) == 2
    for buyer in payload["buyers"]:
        assert buyer["steps"]
        assert buyer["transcript"]
        assert isinstance(buyer["outcome"], str)


async def test_an_unreachable_marketplace_propagates_for_exit_code_1() -> None:
    market = fake_marketplace()
    market.healthy = False
    with pytest.raises(MarketplaceUnavailable):
        await run_scenario(scenario_config(), client=market, clock=FixedClock(NOW))


def test_cli_requires_a_marketplace_url() -> None:
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["run"])
    assert excinfo.value.code == 2


def test_cli_rejects_a_buyer_count_outside_the_profiles() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "run",
                "--marketplace-url",
                "http://fake-market",
                "--buyers",
                "9",
            ]
        )
    assert excinfo.value.code == 2
