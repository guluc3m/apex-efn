"""Cron spec parsing, validation and next-slot maths (no wall clock)."""

from datetime import UTC, datetime

import pytest

from apex.workers.scheduler import CronSpec, JobDefinition, ScheduleError, slot_key


def test_parse_wildcards_and_lists() -> None:
    spec = CronSpec.parse("30 2 * * 1,3")
    assert spec.minute == frozenset({30})
    assert spec.hour == frozenset({2})
    assert spec.weekday == frozenset({1, 3})
    assert spec.day is None and spec.month is None


@pytest.mark.parametrize(
    "bad",
    [
        "* * * *",  # too few fields
        "* * * * * *",  # too many fields
        "60 * * * *",  # minute out of range
        "* 24 * * *",  # hour out of range
        "* * 0 * *",  # day out of range
        "* * 32 * *",  # day out of range
        "* * * 13 *",  # month out of range
        "* * * * 7",  # weekday out of range
        "x * * * *",  # not an integer
        "*/5 * * * *",  # steps are not supported
        "1-5 * * * *",  # ranges are not supported
    ],
)
def test_invalid_expressions_are_rejected(bad: str) -> None:
    with pytest.raises(ScheduleError):
        CronSpec.parse(bad)


def test_empty_field_set_is_rejected() -> None:
    with pytest.raises(ScheduleError):
        CronSpec(minute=frozenset())


def test_matches_uses_utc() -> None:
    spec = CronSpec.parse("0 6 * * *")
    assert spec.matches(datetime(2026, 3, 1, 6, 0, tzinfo=UTC))
    assert not spec.matches(datetime(2026, 3, 1, 6, 1, tzinfo=UTC))


def test_next_after_returns_strictly_later_minute() -> None:
    spec = CronSpec.parse("0 6 * * *")
    after = datetime(2026, 3, 1, 6, 0, 30, tzinfo=UTC)
    assert spec.next_after(after) == datetime(2026, 3, 2, 6, 0, tzinfo=UTC)


def test_next_after_respects_weekday() -> None:
    # 2026-03-01 is a Sunday (weekday 6). Weekday 0 is Monday, and it is the fifth field.
    spec = CronSpec.parse("0 9 * * 0")
    assert spec.weekday == frozenset({0})
    assert spec.next_after(datetime(2026, 3, 1, 0, 0, tzinfo=UTC)) == datetime(
        2026, 3, 2, 9, 0, tzinfo=UTC
    )


def test_field_order_is_minute_hour_day_month_weekday() -> None:
    # 15 March 2026 is a Sunday. "0 6 15 3 *" fires at 06:00 on the 15th of March only.
    spec = CronSpec.parse("0 6 15 3 *")
    assert spec.day == frozenset({15})
    assert spec.month == frozenset({3})
    assert spec.weekday is None
    assert spec.matches(datetime(2026, 3, 15, 6, 0, tzinfo=UTC))
    assert not spec.matches(datetime(2026, 4, 15, 6, 0, tzinfo=UTC))


def test_next_after_raises_when_no_slot_in_horizon() -> None:
    spec = CronSpec.parse("0 0 31 2 *")  # 31 February never happens
    with pytest.raises(ScheduleError):
        spec.next_after(datetime(2026, 1, 1, tzinfo=UTC), horizon_days=400)


def test_slot_key_is_deterministic_and_minute_precise() -> None:
    a = slot_key("fx_ingestion", datetime(2026, 3, 1, 6, 0, 0, tzinfo=UTC))
    b = slot_key("fx_ingestion", datetime(2026, 3, 1, 6, 0, 59, tzinfo=UTC))
    c = slot_key("fx_ingestion", datetime(2026, 3, 1, 6, 1, tzinfo=UTC))
    assert a == b == "fx_ingestion:20260301T0600"
    assert a != c


def test_job_name_must_be_snake_case() -> None:
    async def noop(clock: object) -> dict[str, object]:
        return {}

    with pytest.raises(ScheduleError):
        JobDefinition(name="bad name!", schedule=CronSpec.parse("* * * * *"), func=noop)
    with pytest.raises(ScheduleError):
        JobDefinition(name="ok_name", schedule=CronSpec.parse("* * * * *"), func=noop, max_tries=0)
