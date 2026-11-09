"""Storage for normalised sourcing requests.

The contract's ``POST /v1/missions`` takes only a ``sourcing_request_id`` (see
``contracts/openapi.yaml``), so the request has to outlive the call that created it. This port is that
store; the in-memory implementation serves until D2-05's data layer replaces it.
"""

from __future__ import annotations

from typing import Protocol

from apex.agents.sourcing import SourcingRequest


class SourcingRequestStore(Protocol):
    """Tenant-scoped: an implementation must never return another tenant's request."""

    async def add(self, request: SourcingRequest) -> SourcingRequest: ...

    async def get(self, tenant_id: str, request_id: str) -> SourcingRequest | None: ...


class InMemorySourcingRequestStore:
    def __init__(self) -> None:
        self._requests: dict[tuple[str, str], SourcingRequest] = {}

    async def add(self, request: SourcingRequest) -> SourcingRequest:
        self._requests[(request.tenant_id, request.id)] = request
        return request

    async def get(self, tenant_id: str, request_id: str) -> SourcingRequest | None:
        return self._requests.get((tenant_id, request_id))


__all__ = ["InMemorySourcingRequestStore", "SourcingRequestStore"]
