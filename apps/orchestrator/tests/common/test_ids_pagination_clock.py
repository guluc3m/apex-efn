"""Clock, sortable ids and cursor pagination helpers."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from apex.common import Cursor, FixedClock, IdGenerator, Page, Problem, parse_limit
from apex.common.clock import SystemClock


def test_fixed_clock_moves_forward_only() -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    assert clock.advance(timedelta(minutes=15)) == datetime(2026, 1, 1, 0, 15, tzinfo=UTC)
    with pytest.raises(ValueError):
        clock.advance(timedelta(seconds=-1))


def test_clock_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 1, 1))


def test_system_clock_returns_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_ids_are_26_chars_and_sortable_by_time() -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    gen = IdGenerator(clock, random_bits=lambda n: 0)
    first = gen.new_id()
    clock.advance(timedelta(milliseconds=1))
    second = gen.new_id()
    assert len(first) == 26
    assert first < second


def test_ids_are_deterministic_with_injected_randomness() -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    a = IdGenerator(clock, random_bits=lambda n: 12345).new_id()
    b = IdGenerator(clock, random_bits=lambda n: 12345).new_id()
    assert a == b


def test_ids_differ_with_different_randomness() -> None:
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    a = IdGenerator(clock, random_bits=lambda n: 1).new_id()
    b = IdGenerator(clock, random_bits=lambda n: 2).new_id()
    assert a != b


def test_cursor_round_trip() -> None:
    token = Cursor.encode({"created_at": "2026-01-01T00:00:00Z", "id": "abc"})
    assert "=" not in token
    assert Cursor.decode(token) == {"created_at": "2026-01-01T00:00:00Z", "id": "abc"}


@pytest.mark.parametrize("bad", ["", "!!!", "x" * 600, "bm90LWFuLW9iamVjdA"])
def test_cursor_rejects_malformed(bad: str) -> None:
    with pytest.raises(Problem) as info:
        Cursor.decode(bad)
    assert info.value.status == 400


def test_parse_limit_defaults_and_bounds() -> None:
    assert parse_limit(None, default=20, maximum=100) == 20
    assert parse_limit(100, default=20, maximum=100) == 100
    with pytest.raises(Problem) as too_big:
        parse_limit(101, default=20, maximum=100)
    assert too_big.value.status == 422
    with pytest.raises(Problem):
        parse_limit(0, default=20, maximum=100)


def test_parse_limit_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        parse_limit(None, default=200, maximum=100)


class Item(BaseModel):
    name: str


def test_page_model_serializes_items_and_cursor() -> None:
    page = Page[Item](items=[Item(name="a")], next_cursor=None)
    assert page.model_dump() == {"items": [{"name": "a"}], "next_cursor": None}
