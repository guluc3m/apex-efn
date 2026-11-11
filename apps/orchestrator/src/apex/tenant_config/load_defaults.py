"""CLI: seed the v1 tenant configuration baseline for the given tenants.

Usage::

    python -m apex.tenant_config.load_defaults <tenant_id> [<tenant_id> ...]
    APEX_TENANT_IDS=t1,t2 python -m apex.tenant_config.load_defaults

Used by ``dev:reset`` after the DB seed (D2-03). Until ``apex.db`` exists (D2-05) the only repository
is in-memory, so this command validates the defaults and reports what it *would* seed, but it persists
nothing. The DB path is a TODO and is intentionally not faked.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import logging
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from apex.tenant_config.defaults import DEFAULT_PATH, load_global_layer
from apex.tenant_config.models import TenantConfig
from apex.tenant_config.ports import ConfigVersionRecord
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.resolver import deep_merge
from apex.tenant_config.service import _version_hash

log = logging.getLogger("apex.tenant_config.load_defaults")

TENANT_ENV = "APEX_TENANT_IDS"


def _demo_negotiation(aggressiveness: str, tone: str, counterparts: list[str]) -> dict[str, object]:
    return {
        "aggressiveness": aggressiveness,
        "tone": tone,
        "language": "es",
        "accepts_counterparts": counterparts,
    }


_DEMO_HARD_CONSTRAINTS: dict[str, object] = {
    "banned_platforms": [],
    "banned_countries": [],
    "required_certifications": [],
    "min_accepted_seller_band": "medium",
}


DEMO_VALUES: dict[str, object] = {
    "neg": {"target_discount": "0.08", "max_discount": "0.15"},
    "approval": {
        "threshold": {"amount_minor": 500_000, "currency": "EUR"},
        "dual_control_above": {"amount_minor": 2_000_000, "currency": "EUR"},
    },
    "signing": {"high_value_reauth_above": {"amount_minor": 1_000_000, "currency": "EUR"}},
    # Issue #379: demo ranking profiles after the dominant weights of spec §2. Real tenants set their own.
    "scoring": {
        "profiles": {
            "founder": {
                "name": "Founder",
                "weights": {
                    "landed_cost": "0.5",
                    "seller_confidence": "0.3",
                    "financial_fit": "0.2",
                },
                "negotiation": _demo_negotiation("aggressive", "friendly", ["higher_volume"]),
                "hard_constraints": _DEMO_HARD_CONSTRAINTS,
            },
            "buyer": {
                "name": "Operational buyer",
                "weights": {"lead_time": "0.4", "seller_confidence": "0.4", "landed_cost": "0.2"},
                "negotiation": _demo_negotiation(
                    "balanced", "formal", ["higher_volume", "framework_contract"]
                ),
                "hard_constraints": _DEMO_HARD_CONSTRAINTS,
            },
            "cfo": {
                "name": "CFO",
                "weights": {
                    "financial_fit": "0.5",
                    "landed_cost": "0.3",
                    "seller_confidence": "0.2",
                },
                "negotiation": _demo_negotiation("conservative", "formal", []),
                "hard_constraints": _DEMO_HARD_CONSTRAINTS,
            },
        }
    },
}
"""ADR-900 Q7: demo values for the two demo tenants. They live in the *seed*, never in
``/config/defaults``, so a real tenant starts with these keys unset and must set them in onboarding.
EUR 5,000 / 20,000 / 10,000 in minor units; discounts as decimal fractions (8% and 15%)."""

DEMO_TENANTS: frozenset[str] = frozenset({"tenant-a", "tenant-b"})


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
    tenant_ids: Sequence[str],
    repo: InMemoryConfigRepository,
    *,
    demo_values: bool = False,
) -> list[ConfigVersionRecord]:
    """Write the v1 baseline version (``config_version`` 1) for each tenant that has none yet.

    The baseline carries no tenant overrides: its ``values`` is empty and its ``content_hash`` is the
    hash of the effective global defaults. Idempotent: an existing version is left untouched.

    With ``demo_values`` the two demo tenants (``tenant-a``, ``tenant-b``) get the ADR-900 Q7 demo values in
    their baseline; any other tenant id is left with the keys unset.
    """
    _, global_values = load_global_layer(DEFAULT_PATH)
    TenantConfig.from_mapping(global_values)  # fail fast if the shipped defaults are invalid
    clock = _SystemClock()
    written: list[ConfigVersionRecord] = []
    for tid in tenant_ids:
        if await repo.latest_version(tid) is not None:
            log.info("tenant %s already has configuration; skipping", tid)
            continue
        values = copy.deepcopy(DEMO_VALUES) if demo_values and tid in DEMO_TENANTS else {}
        TenantConfig.from_mapping(
            deep_merge(global_values, values)
        )  # the demo values must be valid
        record = ConfigVersionRecord(
            tenant_id=tid,
            config_version=1,
            content_hash=_version_hash(global_values, values),
            values=values,
            created_at=clock.now(),
            decision_id=None,
        )
        await repo.append_version(record)
        written.append(record)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m apex.tenant_config.load_defaults")
    parser.add_argument("tenant_ids", nargs="*", help="tenant ids (or set APEX_TENANT_IDS)")
    parser.add_argument(
        "--demo-values",
        action="store_true",
        help="give tenant-a and tenant-b the ADR-900 Q7 demo values (never used for real tenants)",
    )
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
    written = asyncio.run(seed(tenant_ids, repo, demo_values=args.demo_values))
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
