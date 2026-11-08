"""CLI: seed the v1 tenant configuration baseline for the given tenants.

Usage::

    python -m apex.tenant_config.load_defaults <tenant_id> [<tenant_id> ...]
    APEX-EFN_TENANT_IDS=t1,t2 python -m apex.tenant_config.load_defaults

Used by ``dev:reset`` after the DB seed (D2-03). Until ``apex.db`` exists (D2-05) the only repository
is in-memory, so this command validates the defaults and reports what it *would* seed, but it persists
nothing. The DB path is a TODO and is intentionally not faked.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from apex.tenant_config.defaults import DEFAULT_PATH, load_global_layer
from apex.tenant_config.models import TenantConfig
from apex.tenant_config.ports import ConfigVersionRecord
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.service import _version_hash

log = logging.getLogger("apex.tenant_config.load_defaults")

TENANT_ENV = "APEX-EFN_TENANT_IDS"


class _SystemClock:
    """Clock for the CLI entry point only (the library never reads wall time itself)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


def _tenant_ids(argv: Sequence[str]) -> list[str]:
    ids = [t.strip() for t in argv if t.strip()]
    if not ids:
        ids = [t.strip() for t in os.environ.get(TENANT_ENV, "").split(",") if t.strip()]
    # stable, de-duplicated order
    seen: dict[str, None] = {}
    for tid in ids:
        seen.setdefault(tid, None)
    return list(seen)


async def seed(
    tenant_ids: Sequence[str], repo: InMemoryConfigRepository
) -> list[ConfigVersionRecord]:
    """Write the v1 baseline version (``config_version`` 1) for each tenant that has none yet.

    The baseline carries no tenant overrides: its ``values`` is empty and its ``content_hash`` is the
    hash of the effective global defaults. Idempotent: an existing version is left untouched.
    """
    _, global_values = load_global_layer(DEFAULT_PATH)
    TenantConfig.from_mapping(global_values)  # fail fast if the shipped defaults are invalid
    digest = _version_hash(global_values, {})
    clock = _SystemClock()
    written: list[ConfigVersionRecord] = []
    for tid in tenant_ids:
        if await repo.latest_version(tid) is not None:
            log.info("tenant %s already has configuration; skipping", tid)
            continue
        record = ConfigVersionRecord(
            tenant_id=tid,
            config_version=1,
            content_hash=digest,
            values={},
            created_at=clock.now(),
            decision_id=None,
        )
        await repo.append_version(record)
        written.append(record)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m apex.tenant_config.load_defaults")
    parser.add_argument("tenant_ids", nargs="*", help="tenant ids (or set APEX-EFN_TENANT_IDS)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    tenant_ids = _tenant_ids(args.tenant_ids)
    if not tenant_ids:
        log.error("no tenant ids given (args or %s)", TENANT_ENV)
        return 2

    log.warning(
        "no database repository yet (TODO D2-05): seeding IN-MEMORY only, nothing is persisted"
    )
    repo = InMemoryConfigRepository()
    written = asyncio.run(seed(tenant_ids, repo))
    for rec in written:
        log.info(
            "would seed tenant %s at config_version %d (%s)",
            rec.tenant_id,
            rec.config_version,
            rec.content_hash,
        )
    print(
        f"validated v1 defaults for {len(tenant_ids)} tenant(s); persisted: 0 (in-memory, TODO D2-05)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
