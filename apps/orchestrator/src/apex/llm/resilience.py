"""Retries with jitter, per-endpoint circuit breaker, and fallback chain (spec §5.6).

- Backoff uses *full jitter*: ``sleep = uniform(0, min(cap, base * 2**attempt))`` drawn from an injected,
  seedable RNG, so tests are deterministic. ``Retry-After`` from the server is honoured as a lower bound.
- Sleep is injectable (``Sleeper``) so tests never really sleep.
- The circuit breaker is time-based on the injected :class:`apex.common.clock.Clock`:
  closed -> open after ``failure_threshold`` consecutive failures; open -> half-open once
  ``open_seconds`` have elapsed; half-open admits one probe: success closes, failure re-opens.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, TypeVar

from apex.common.clock import Clock
from apex.llm.config import ResilienceConfig
from apex.llm.transport import LLMHTTPError, LLMTransportError

T = TypeVar("T")


class Sleeper(Protocol):
    async def __call__(self, seconds: float) -> None: ...


async def _real_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    def __init__(self, endpoint_id: str) -> None:
        self.endpoint_id = endpoint_id
        super().__init__(f"circuit open for endpoint {endpoint_id}")


class AllEndpointsUnavailableError(Exception):
    """Every endpoint in the fallback chain failed or has an open circuit."""

    def __init__(self, chain: list[str], causes: dict[str, str]) -> None:
        self.chain = chain
        self.causes = causes
        super().__init__(f"all endpoints unavailable: {causes}")


@dataclass
class CircuitBreaker:
    endpoint_id: str
    failure_threshold: int
    open_seconds: float
    clock: Clock
    state: BreakerState = BreakerState.CLOSED
    _failures: int = 0
    _opened_at: datetime | None = field(default=None, repr=False)
    _probe_in_flight: bool = field(default=False, repr=False)

    def _refresh(self) -> None:
        if (
            self.state is BreakerState.OPEN
            and self._opened_at is not None
            and self.clock.now() - self._opened_at >= timedelta(seconds=self.open_seconds)
        ):
            self.state = BreakerState.HALF_OPEN
            self._probe_in_flight = False

    def allow(self) -> bool:
        """Whether a call may be attempted now. In half-open, only one probe is admitted."""
        self._refresh()
        if self.state is BreakerState.CLOSED:
            return True
        if self.state is BreakerState.OPEN:
            return False
        if self._probe_in_flight:
            return False
        self._probe_in_flight = True
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._probe_in_flight = False
        self.state = BreakerState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._probe_in_flight = False
        if self.state is BreakerState.HALF_OPEN:
            self._open()
            return
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self.state = BreakerState.OPEN
        self._opened_at = self.clock.now()
        self._failures = 0


class BreakerRegistry:
    """One breaker per endpoint id, sharing thresholds and the clock."""

    def __init__(self, config: ResilienceConfig, clock: Clock) -> None:
        self._config = config
        self._clock = clock
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, endpoint_id: str) -> CircuitBreaker:
        if endpoint_id not in self._breakers:
            self._breakers[endpoint_id] = CircuitBreaker(
                endpoint_id=endpoint_id,
                failure_threshold=self._config.breaker_failure_threshold,
                open_seconds=self._config.breaker_open_seconds,
                clock=self._clock,
            )
        return self._breakers[endpoint_id]


def full_jitter_delay(
    attempt: int,
    *,
    base_s: float,
    cap_s: float,
    rng: random.Random,
    retry_after_s: float | None = None,
) -> float:
    """Full-jitter backoff for the given 0-based retry attempt; ``Retry-After`` is a lower bound."""
    ceiling = min(cap_s, base_s * (2**attempt))
    delay = rng.uniform(0.0, ceiling) if ceiling > 0 else 0.0
    if retry_after_s is not None:
        delay = max(delay, retry_after_s)
    return delay


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, LLMHTTPError):
        return exc.is_retryable
    return isinstance(exc, LLMTransportError)


class Resilience:
    """Runs an async call against one endpoint with retries and breaker bookkeeping."""

    def __init__(
        self,
        config: ResilienceConfig,
        clock: Clock,
        *,
        rng: random.Random | None = None,
        sleep: Sleeper | None = None,
    ) -> None:
        self._config = config
        self._rng = rng or random.Random(0)
        self._sleep: Sleeper = sleep or _real_sleep
        self.breakers = BreakerRegistry(config, clock)

    async def call(self, endpoint_id: str, fn: Callable[[], Awaitable[T]]) -> T:
        breaker = self.breakers.get(endpoint_id)
        if not breaker.allow():
            raise CircuitOpenError(endpoint_id)
        attempt = 0
        while True:
            try:
                result = await fn()
            except (LLMHTTPError, LLMTransportError) as exc:
                if not is_retryable(exc):
                    # Client errors (e.g. 400, 401) are not endpoint health problems to retry.
                    breaker.record_success()
                    raise
                breaker.record_failure()
                if attempt >= self._config.max_retries or breaker.state is BreakerState.OPEN:
                    raise
                retry_after = exc.retry_after_s if isinstance(exc, LLMHTTPError) else None
                delay = full_jitter_delay(
                    attempt,
                    base_s=self._config.backoff_base_s,
                    cap_s=self._config.backoff_cap_s,
                    rng=self._rng,
                    retry_after_s=retry_after,
                )
                attempt += 1
                await self._sleep(delay)
                if not breaker.allow():
                    raise CircuitOpenError(endpoint_id) from exc
                continue
            breaker.record_success()
            return result


async def run_with_fallback[T](
    chain: list[str],
    attempt_endpoint: Callable[[str], Awaitable[T]],
) -> tuple[str, T]:
    """Try each endpoint in order. Returns (endpoint_id_used, result).

    Circuit-open endpoints are skipped with a recorded cause. Raises
    :class:`AllEndpointsUnavailableError` when the whole chain is exhausted.
    """
    causes: dict[str, str] = {}
    for endpoint_id in chain:
        try:
            return endpoint_id, await attempt_endpoint(endpoint_id)
        except CircuitOpenError:
            causes[endpoint_id] = "circuit_open"
        except LLMHTTPError as exc:
            if not exc.is_retryable and not exc.is_unsupported:
                # A client error (e.g. malformed request) is not an availability problem: surface it.
                raise
            causes[endpoint_id] = f"LLMHTTPError:{exc.status_code}"
        except LLMTransportError as exc:
            causes[endpoint_id] = f"LLMTransportError:{exc.reason}"
    raise AllEndpointsUnavailableError(chain, causes)


__all__ = [
    "AllEndpointsUnavailableError",
    "BreakerRegistry",
    "BreakerState",
    "CircuitBreaker",
    "CircuitOpenError",
    "Resilience",
    "Sleeper",
    "full_jitter_delay",
    "is_retryable",
    "run_with_fallback",
]
