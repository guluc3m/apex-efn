"""Anchor the chain head to S3 Object Lock in compliance mode (D2-10).

The anchor object is immutable until ``retain_until``, so rewriting the whole chain (including recomputed hashes)
still fails verification: the anchored head hash no longer matches the event at that ``seq``.
The store is injected: ``Boto3AnchorStore`` in production, a fake in tests. Retention is a caller parameter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apex.audit import chain
from apex.db.models import AuditEvent


class AnchorStore(Protocol):
    def put(self, key: str, body: bytes, retain_until: datetime) -> None:
        """Write ``key`` with Object Lock COMPLIANCE retention until ``retain_until``."""

    def latest(self, prefix: str) -> tuple[str, bytes] | None:
        """The object under ``prefix`` with the greatest key, or None."""


class Boto3AnchorStore:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client, self.bucket = client, bucket

    def put(self, key: str, body: bytes, retain_until: datetime) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ObjectLockMode="COMPLIANCE",
            ObjectLockRetainUntilDate=retain_until,
        )

    def latest(self, prefix: str) -> tuple[str, bytes] | None:
        # ponytail: one list page (1000 keys); zero-padded seq keys sort by seq. Paginate if anchors exceed it.
        listing = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        keys = sorted(item["Key"] for item in listing.get("Contents", []))
        if not keys:
            return None
        body = self.client.get_object(Bucket=self.bucket, Key=keys[-1])["Body"].read()
        return keys[-1], body


def _prefix(tenant_id: str) -> str:
    return f"anchors/{tenant_id}/"


async def anchor_head(
    session: AsyncSession,
    store: AnchorStore,
    tenant_id: str,
    *,
    now: datetime,
    retention: timedelta,
) -> chain.ChainCheck:
    """Verify the chain, then anchor its head. A broken or empty chain is never anchored."""
    check = await chain.verify(session, tenant_id)
    if not check.valid or check.head_hash is None:
        return check
    body = json.dumps(
        {
            "tenant_id": tenant_id,
            "seq": check.checked,
            "hash": check.head_hash,
            "anchored_at": now.isoformat(),
        },
        sort_keys=True,
    ).encode()
    store.put(f"{_prefix(tenant_id)}{check.checked:020d}.json", body, now + retention)
    return check


@dataclass(frozen=True)
class Anchored:
    seq: int
    hash: str
    at: datetime


def read_anchor(store: AnchorStore, tenant_id: str) -> Anchored | None:
    found = store.latest(_prefix(tenant_id))
    if found is None:
        return None
    data = json.loads(found[1])
    return Anchored(data["seq"], data["hash"], datetime.fromisoformat(data["anchored_at"]))


async def anchor_matches(session: AsyncSession, tenant_id: str, anchored: Anchored) -> bool:
    stored = await session.scalar(
        select(AuditEvent.hash).where(
            AuditEvent.tenant_id == tenant_id, AuditEvent.seq == anchored.seq
        )
    )
    return stored == anchored.hash
