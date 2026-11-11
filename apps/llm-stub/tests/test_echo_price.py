"""The `echo_price` response used by the simulation (D5-11).

The point is that no number is invented: the "model" repeats the price the prompt pinned, and says something
neutral when the prompt states none (the buyer drafter then falls back to its deterministic template).
"""

from __future__ import annotations

from llm_stub.models import ChatMessage
from llm_stub.render import echo_price_text, extract_money


def test_extracts_the_first_price_in_the_prompt() -> None:
    assert extract_money("Could you do EUR 4.10 for 5000 units?") == "EUR 4.10"
    assert extract_money("EUR 4,10 per unit") == "EUR 4.10"
    assert extract_money("no price mentioned") is None
    assert extract_money("价格 4.20 EUR") == "EUR 4.20"


def test_echoes_the_pinned_price() -> None:
    messages = [ChatMessage(role="user", content="Propose EUR 4.10 as the counter-offer.")]
    text = echo_price_text(messages)
    assert "EUR 4.10" in text
    assert text.startswith("Understood.")


def test_says_something_neutral_when_no_price_is_given() -> None:
    buyer = echo_price_text([ChatMessage(role="user", content="Hello there")], role="buyer")
    seller = echo_price_text([ChatMessage(role="user", content="Hello there")], role="seller")
    assert buyer.startswith("Hello,")
    assert seller.startswith("Thanks")
    for text in (buyer, seller):
        assert "EUR" not in text and "USD" not in text and "CNY" not in text
