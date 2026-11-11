"""Per-platform chat routing: an offer haggles on the platform that published it."""

from __future__ import annotations

from typing import Any

from apex.negotiation.ports import ChatLine
from apex.negotiation.sim.mock_a import PerPlatformChatTransport


class _Transport:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[str, Any]] = []

    async def open(self, *, platform: str, seller_id: str, product_id: str, account_id: str) -> str:
        self.calls.append(("open", platform))
        return f"chat-{platform}-0001"

    async def send(self, chat_id: str, text: str) -> None:
        self.calls.append(("send", chat_id))

    async def read(self, chat_id: str, *, after_seq: int) -> list[ChatLine]:
        self.calls.append(("read", chat_id))
        return [ChatLine(seq=1, role="seller", text="ok")]


async def test_an_offer_opens_its_chat_on_its_own_platform() -> None:
    default = _Transport("mock-c")
    mock_a = _Transport("mock-a")
    chats = PerPlatformChatTransport(default=default, overrides={"mock-a": mock_a})

    chat_id = await chats.open(
        platform="mock-a", seller_id="s-1", product_id="a-1", account_id="acct"
    )
    assert chat_id == "chat-mock-a-0001"
    assert mock_a.calls == [("open", "mock-a")]
    assert default.calls == []


async def test_send_and_read_go_back_to_the_transport_that_opened_the_chat() -> None:
    default = _Transport("mock-c")
    mock_a = _Transport("mock-a")
    chats = PerPlatformChatTransport(default=default, overrides={"mock-a": mock_a})

    await chats.send("chat-mock-a-0001", "hello")
    await chats.read("chat-mock-e-0001", after_seq=3)
    assert mock_a.calls == [("send", "chat-mock-a-0001")]
    assert default.calls == [("read", "chat-mock-e-0001")]
