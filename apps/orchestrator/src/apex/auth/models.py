"""The authenticated caller (D1-05, DEV-1).

``Principal`` is what every router receives: the user, the tenant they belong to and the closed set of
roles held in the access token. Roles are never taken from a request body or a header.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from apex.auth.tokens import KNOWN_ROLES, SIGNING_ROLES


class Principal(BaseModel):
    """The caller behind a request. Immutable: a router cannot change who the caller is."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    roles: tuple[str, ...] = ()
    #: ``auth_time`` from the access token. Keycloak sets it on step-up (ACR) tokens; D2-08 uses it to
    #: anchor a signing session. ``None`` means the token did not carry one.
    auth_time: int | None = None
    #: ``acr`` claim: the Authentication Context Class Reference of this authentication. ``None`` when
    #: the token (or the realm) carries no mapping; ``urn:apex:loa:2`` is the sign-up step-up value
    #: (ADR-900 Q11, ``infra/keycloak/realm-apex.json``). The signature layer still checks freshness.
    acr: str | None = None

    def has_role(self, *names: str) -> bool:
        return any(name in self.roles for name in names)

    @property
    def is_signer(self) -> bool:
        """Whether this principal may sign decisions. ``viewer`` never signs (AGENTS D1-05)."""
        return any(role in SIGNING_ROLES for role in self.roles)

    def __repr__(self) -> str:
        # No claim values beyond the identifiers: a principal may be logged on an error path.
        return f"Principal(user_id={self.user_id!r}, tenant_id={self.tenant_id!r}, roles={self.roles!r})"


__all__ = ["KNOWN_ROLES", "Principal"]
