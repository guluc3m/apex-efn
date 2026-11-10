"""Access-token verification (D1-05, DEV-1).

The algorithm is pinned to RS256 before the token is decoded, so an ``alg=none`` token or an HS256
token signed with the public key (algorithm confusion) is refused without ever reaching a signature
check. Time checks are done here, with an injected clock, instead of inside PyJWT so the behaviour is
deterministic in tests and the skew policy is explicit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

import jwt

from apex.auth.errors import (
    BAD_SIGNATURE,
    EXPIRED,
    JWKS_UNAVAILABLE,
    MALFORMED,
    MISSING_CLAIM,
    NOT_YET_VALID,
    UNSUPPORTED_ALGORITHM,
    WRONG_AUDIENCE,
    WRONG_ISSUER,
    AuthError,
    JwksError,
)
from apex.auth.jwks import JwksProvider
from apex.auth.settings import AuthSettings

ALGORITHM = "RS256"
# Realm roles the platform knows. Anything else a Keycloak token carries (``offline_access``,
# ``uma_authorization``, client roles, ...) is ignored rather than granted.
KNOWN_ROLES: tuple[str, ...] = ("owner", "admin", "buyer", "finance", "viewer")
SIGNING_ROLES: tuple[str, ...] = ("owner", "admin", "buyer", "finance")
_ACCEPTED_TYP = frozenset({"JWT", "at+jwt"})


@dataclass(frozen=True, slots=True)
class VerifiedToken:
    """The parts of a validated access token the platform relies on."""

    user_id: str
    tenant_id: str
    roles: tuple[str, ...]
    auth_time: int | None
    #: ``acr`` claim (Authentication Context Class Reference). Keycloak emits it through the ``acr``
    #: client scope when the realm maps an ACR value to a Level of Authentication (ADR-900 Q11).
    acr: str | None
    expires_at: datetime
    claims: Mapping[str, Any]

    @property
    def is_signer(self) -> bool:
        return any(role in SIGNING_ROLES for role in self.roles)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _roles_from(claims: Mapping[str, Any]) -> tuple[str, ...]:
    """Closed role set: canonical order, unknown roles dropped.

    Keycloak's default realm-role mapper emits the realm roles, but the same information also lives in
    ``realm_access.roles``; accept both so the verifier does not depend on one client's mapper setup.
    """
    declared: Any = claims.get("roles")
    if declared is None:
        realm_access = claims.get("realm_access")
        if isinstance(realm_access, Mapping):
            declared = realm_access.get("roles")
    if not isinstance(declared, (list, tuple)):
        declared = ()
    present = {role for role in declared if isinstance(role, str)}
    return tuple(role for role in KNOWN_ROLES if role in present)


async def verify_access_token(
    token: str,
    *,
    provider: JwksProvider,
    settings: AuthSettings,
    now: datetime | None = None,
) -> VerifiedToken:
    """Verify a bearer access token or raise :class:`AuthError` with a closed reason."""
    if not isinstance(token, str) or not token:
        raise AuthError(MALFORMED)

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthError(MALFORMED) from exc

    if header.get("alg") != ALGORITHM:
        raise AuthError(UNSUPPORTED_ALGORITHM)
    token_type = header.get("typ")
    if token_type is not None and token_type not in _ACCEPTED_TYP:
        raise AuthError(MALFORMED)
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise AuthError(MALFORMED)

    try:
        key = await provider.key_for(kid)
    except JwksError as exc:
        raise AuthError(JWKS_UNAVAILABLE) from exc

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=[ALGORITHM],
            audience=settings.audience,
            issuer=settings.issuer,
            options={
                # Time is validated below against the injected clock.
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
                "require": ["exp", "iat", "iss", "aud", "sub"],
            },
        )
    except jwt.InvalidIssuerError as exc:
        raise AuthError(WRONG_ISSUER) from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthError(WRONG_AUDIENCE) from exc
    except jwt.InvalidSignatureError as exc:
        raise AuthError(BAD_SIGNATURE) from exc
    except jwt.MissingRequiredClaimError as exc:
        raise AuthError(MISSING_CLAIM) from exc
    except jwt.PyJWTError as exc:
        raise AuthError(MALFORMED) from exc

    current = now or datetime.now(UTC)
    now_ts = current.timestamp()
    skew = settings.clock_skew_seconds

    exp = _as_int(claims.get("exp"))
    iat = _as_int(claims.get("iat"))
    nbf = claims.get("nbf")
    if exp is None or iat is None:
        raise AuthError(MALFORMED)
    if nbf is not None and _as_int(nbf) is None:
        raise AuthError(MALFORMED)

    if now_ts > exp + skew:
        raise AuthError(EXPIRED)
    if iat > now_ts + skew:
        raise AuthError(NOT_YET_VALID)
    if nbf is not None and int(nbf) > now_ts + skew:
        raise AuthError(NOT_YET_VALID)

    subject = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    if subject is None:
        raise AuthError(MISSING_CLAIM)
    if not isinstance(subject, str) or not subject:
        raise AuthError(MALFORMED)
    if tenant_id is None:
        raise AuthError(MISSING_CLAIM)
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise AuthError(MALFORMED)

    auth_time = claims.get("auth_time")
    if auth_time is not None and _as_int(auth_time) is None:
        raise AuthError(MALFORMED)

    acr = claims.get("acr")
    if acr is not None and not isinstance(acr, str):
        raise AuthError(MALFORMED)

    return VerifiedToken(
        user_id=subject,
        tenant_id=tenant_id,
        roles=_roles_from(claims),
        auth_time=_as_int(auth_time),
        acr=acr,
        expires_at=datetime.fromtimestamp(exp, UTC),
        claims=MappingProxyType(dict(claims)),
    )


__all__ = ["ALGORITHM", "KNOWN_ROLES", "SIGNING_ROLES", "VerifiedToken", "verify_access_token"]
