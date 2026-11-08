"""Feature flags over the Unleash client API. Fail closed: unknown, unreachable or unsupported means off.

Naming convention and defaults: docs/observability/flags.md. Keep this file in sync with
apps/browser-worker/src/platform/flags.ts.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("trato.platform.flags")

DEFAULT_APP_NAME = "trato-orchestrator"

_SEGMENT = r"[a-z0-9_-]+"
_FLAG_PATTERNS = (
    re.compile(rf"platform\.{_SEGMENT}\.enabled"),
    re.compile(rf"negotiation\.strategy\.{_SEGMENT}"),
    re.compile(r"negotiation\.autonomous_send"),
    re.compile(rf"sanity\.bands\.{_SEGMENT}"),
    re.compile(rf"trust\.model\.{_SEGMENT}"),
)
_ROLLOUT_RE = re.compile(r"\d{1,3}")


def validate_flag_name(name: str) -> str:
    if not any(pattern.fullmatch(name) for pattern in _FLAG_PATTERNS):
        raise ValueError(f"malformed feature flag name {name!r}; see docs/observability/flags.md")
    return name


def platform_flag_name(platform_id: str) -> str:
    return validate_flag_name(f"platform.{platform_id}.enabled")


class FlagProvider(Protocol):
    def is_enabled(self, name: str, context: Mapping[str, str] | None = None) -> bool: ...

    def is_platform_enabled(self, platform_id: str) -> bool: ...


class StaticFlags:
    """In-memory provider for tests and local tooling. Flags not listed are off."""

    def __init__(self, flags: Mapping[str, bool] | None = None) -> None:
        self._flags = {validate_flag_name(name): value for name, value in (flags or {}).items()}

    def is_enabled(self, name: str, context: Mapping[str, str] | None = None) -> bool:
        validate_flag_name(name)
        return self._flags.get(name, False)

    def is_platform_enabled(self, platform_id: str) -> bool:
        return self.is_enabled(platform_flag_name(platform_id))


class _Strategy(BaseModel):
    name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    constraints: list[Any] = Field(default_factory=list)
    segments: list[Any] = Field(default_factory=list)
    disabled: bool = False


class _Feature(BaseModel):
    name: str
    enabled: bool
    strategies: list[_Strategy] = Field(default_factory=list)


class _FeaturesPayload(BaseModel):
    features: list[_Feature]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class UnleashFlags:
    """Reads toggles from `GET {base_url}/client/features` and keeps the last good snapshot."""

    def __init__(
        self,
        *,
        base_url: str,
        client_token: str,
        app_name: str = DEFAULT_APP_NAME,
        instance_id: str = DEFAULT_APP_NAME,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 5.0,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/client/features"
        self._headers = {
            "Authorization": client_token,
            "UNLEASH-APPNAME": app_name,
            "UNLEASH-INSTANCEID": instance_id,
            "Accept": "application/json",
        }
        self._http = httpx.Client(transport=transport, timeout=timeout_seconds)
        self._clock = clock
        self._snapshot: dict[str, _Feature] = {}
        self._last_refreshed_at: datetime | None = None
        self._warned: set[str] = set()

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        app_name: str = DEFAULT_APP_NAME,
        transport: httpx.BaseTransport | None = None,
    ) -> UnleashFlags:
        source = os.environ if env is None else env
        url = source.get("UNLEASH_URL")
        token = source.get("UNLEASH_API_TOKEN")
        if not url or not token:
            raise ValueError("UNLEASH_URL and UNLEASH_API_TOKEN must be set")
        return cls(base_url=url, client_token=token, app_name=app_name, transport=transport)

    @property
    def last_refreshed_at(self) -> datetime | None:
        return self._last_refreshed_at

    def refresh(self) -> bool:
        try:
            response = self._http.get(self._url, headers=self._headers)
            response.raise_for_status()
            payload = _FeaturesPayload.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "feature flag refresh failed (%s: %s); keeping last snapshot of %d flags",
                type(exc).__name__,
                exc,
                len(self._snapshot),
            )
            return False
        self._snapshot = {feature.name: feature for feature in payload.features}
        self._last_refreshed_at = self._clock()
        return True

    async def poll(self, interval_seconds: float, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await asyncio.to_thread(self.refresh)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)

    def close(self) -> None:
        self._http.close()

    def is_enabled(self, name: str, context: Mapping[str, str] | None = None) -> bool:
        validate_flag_name(name)
        feature = self._snapshot.get(name)
        if feature is None or not feature.enabled:
            return False
        if not feature.strategies:
            return True
        return any(self._evaluate(strategy, name) for strategy in feature.strategies)

    def is_platform_enabled(self, platform_id: str) -> bool:
        return self.is_enabled(platform_flag_name(platform_id))

    def _evaluate(self, strategy: _Strategy, flag: str) -> bool:
        if strategy.disabled:
            return False
        if strategy.constraints or strategy.segments:
            self._warn_once(
                f"{flag}|{strategy.name}|constraints", "constraints/segments unsupported"
            )
            return False
        if strategy.name == "default":
            return True
        if strategy.name == "flexibleRollout":
            return self._rollout(strategy.parameters.get("rollout"), flag)
        self._warn_once(f"{flag}|{strategy.name}", f"strategy {strategy.name!r} unsupported")
        return False

    def _rollout(self, rollout: Any, flag: str) -> bool:
        text = str(rollout)
        if _ROLLOUT_RE.fullmatch(text) is None:
            self._warn_once(f"{flag}|rollout", f"rollout value {text!r} unsupported")
            return False
        percent = int(text)
        if percent == 100:
            return True
        if percent == 0:
            return False
        self._warn_once(
            f"{flag}|rollout", f"partial rollout {percent}% unsupported, treated as off"
        )
        return False

    def _warn_once(self, key: str, message: str) -> None:
        if key in self._warned:
            return
        self._warned.add(key)
        logger.warning("feature flag: %s (fail closed)", message)
