"""JWKS retrieval and caching for access-token verification (D1-05, DEV-1).

The key set is fetched lazily from ``APEX_AUTH_JWKS_URL`` and cached for a TTL. A token signed with a
key identifier (``kid``) that is not in the cache triggers one refetch, rate limited by a cooldown so a
stream of bogus tokens cannot turn into a stream of requests against the identity provider.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt

from apex.auth.errors import UNKNOWN_KEY, AuthError, JwksError
from apex.auth.settings import AuthSettings

logger = logging.getLogger(__name__)

Clock = Callable[[], float]


def _usable_keys(payload: Any) -> dict[str, Any]:
    """Return ``{kid: public_key}`` for the RSA signing keys of a JWKS document."""
    if not isinstance(payload, dict):
        raise JwksError(JwksError.INVALID_DOCUMENT)
    keys = payload.get("keys")
    if not isinstance(keys, list):
        raise JwksError(JwksError.INVALID_DOCUMENT)

    usable: dict[str, Any] = {}
    for jwk in keys:
        if not isinstance(jwk, dict):
            continue
        if jwk.get("kty") != "RSA":
            continue
        # A JWKS may carry encryption keys too; only signing keys are acceptable here.
        if jwk.get("use") not in (None, "sig"):
            continue
        if jwk.get("alg") not in (None, "RS256"):
            continue
        kid = jwk.get("kid")
        if not isinstance(kid, str) or not kid:
            continue
        try:
            usable[kid] = jwt.PyJWK(jwk, algorithm="RS256").key
        except (jwt.PyJWTError, ValueError, KeyError, TypeError):
            continue
    if not usable:
        raise JwksError(JwksError.NO_USABLE_KEYS)
    return usable


class JwksProvider:
    """Caches the RS256 public keys used to verify bearer tokens.

    ``transport`` lets tests serve a JWKS without a network, and ``clock`` lets them control the TTL and
    the refetch cooldown without sleeping.
    """

    def __init__(
        self,
        settings: AuthSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock = time.monotonic,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._clock = clock
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None
        self._last_refresh_attempt_at: float | None = None
        # Separate from the refresh attempt: the first unknown kid must be able to force one refetch
        # even right after a regular fetch (key rotation), but repeated unknown kids must not.
        self._last_forced_refetch_at: float | None = None
        self._lock = asyncio.Lock()

    async def key_for(self, kid: str) -> Any:
        """Return the public key for ``kid``, fetching or refreshing the key set when needed."""
        now = self._clock()
        if self._is_fresh(now) and kid in self._keys:
            return self._keys[kid]

        async with self._lock:
            now = self._clock()
            if self._is_fresh(now) and kid in self._keys:
                return self._keys[kid]

            force = self._is_fresh(now)
            if force:
                # Known key set, unknown kid: one rotation refetch per cooldown window.
                if not self._forced_cooldown_elapsed(now):
                    raise AuthError(UNKNOWN_KEY)
                self._last_forced_refetch_at = now
            await self._refresh()

            if kid not in self._keys:
                raise AuthError(UNKNOWN_KEY)
            return self._keys[kid]

    async def keys(self) -> dict[str, Any]:
        """Return the current key set, refreshing it when stale. Used by health checks and tests."""
        if not self._is_fresh(self._clock()):
            async with self._lock:
                if not self._is_fresh(self._clock()):
                    await self._refresh()
        return dict(self._keys)

    def _is_fresh(self, now: float) -> bool:
        return (
            self._fetched_at is not None
            and (now - self._fetched_at) < self._settings.cache_ttl_seconds
        )

    def _forced_cooldown_elapsed(self, now: float) -> bool:
        return (
            self._last_forced_refetch_at is None
            or (now - self._last_forced_refetch_at) >= self._settings.refetch_cooldown_seconds
        )

    async def _refresh(self) -> None:
        """Fetch the key set. A failed refresh keeps the previous keys, if any, so an IdP outage does
        not log every caller out; with no previous keys the failure surfaces as ``jwks_unavailable``."""
        now = self._clock()
        self._last_refresh_attempt_at = now
        try:
            fetched = await self._fetch()
        except JwksError as exc:
            if self._keys:
                logger.warning(
                    "jwks refresh failed (%s); keeping %d cached key(s)",
                    exc.reason,
                    len(self._keys),
                )
                return
            raise
        self._keys = fetched
        self._fetched_at = now

    async def _fetch(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._settings.http_timeout_seconds,
            ) as client:
                response = await client.get(
                    self._settings.jwks_url, headers={"accept": "application/json"}
                )
        except httpx.HTTPError as exc:  # network, timeout, TLS
            raise JwksError(JwksError.UNAVAILABLE) from exc

        if response.status_code != 200:
            raise JwksError(JwksError.UNAVAILABLE)
        try:
            payload = response.json()
        except ValueError as exc:
            raise JwksError(JwksError.INVALID_DOCUMENT) from exc
        return _usable_keys(payload)


__all__ = ["JwksProvider"]
