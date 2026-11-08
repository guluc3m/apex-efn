"""``ConfigRepository`` implementations.

- ``InMemoryConfigRepository``: used by tests and the DB-less CLI path. Enforces append-only and
  monotonic ``config_version`` the same way the DB will (triggers in D2-03).
- ``SqlAlchemyConfigRepository``: TODO pending D2-05 (``apex.db`` does not exist yet). Left as an
  explicit stub that raises, so nothing silently persists to the wrong place.
"""

from __future__ import annotations

from apex.tenant_config.errors import TenantConfigError
from apex.tenant_config.ports import ConfigVersionRecord


class InMemoryConfigRepository:
    """Append-only, in-process store. Satisfies ``ConfigRepository``."""

    def __init__(self) -> None:
        self._versions: dict[str, list[ConfigVersionRecord]] = {}

    async def latest_version(self, tenant_id: str) -> ConfigVersionRecord | None:
        rows = self._versions.get(tenant_id)
        return rows[-1] if rows else None

    async def get_version(self, tenant_id: str, config_version: int) -> ConfigVersionRecord | None:
        for row in self._versions.get(tenant_id, []):
            if row.config_version == config_version:
                return row
        return None

    async def list_versions(self, tenant_id: str) -> list[ConfigVersionRecord]:
        return list(self._versions.get(tenant_id, []))

    async def append_version(self, record: ConfigVersionRecord) -> None:
        rows = self._versions.setdefault(record.tenant_id, [])
        # The baseline (v1) must be stored explicitly by the seed (load_defaults); appends only go on
        # top of an existing version, never create one implicitly (ADR-400 §4).
        expected = 1 if not rows else rows[-1].config_version + 1
        if record.config_version != expected:
            raise TenantConfigError(
                f"tenant {record.tenant_id}: append expects config_version {expected}, "
                f"got {record.config_version} (versions are monotonic, append-only)"
            )
        rows.append(record)


class SqlAlchemyConfigRepository:
    """TODO(D2-05): implement on top of ``apex.db`` (async session + ``tenant_session``).

    Must map to an append-only ``tenant_config_versions`` table (D2-03) with a unique
    ``(tenant_id, config_version)`` constraint and an UPDATE/DELETE-blocking trigger.
    """

    def __init__(self, *_: object, **__: object) -> None:
        raise NotImplementedError("SqlAlchemyConfigRepository is pending D2-05 (apex.db)")
