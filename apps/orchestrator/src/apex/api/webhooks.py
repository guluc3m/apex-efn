"""Platform webhooks (owner: DEV-5, D5-11).

Authenticated by an HMAC signature over the raw body, not by a user token: a marketplace calls us and has no
principal. The route reads the raw bytes before parsing so the signature covers exactly what was sent.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse

from apex.common.errors import Problem
from apex.negotiation.webhooks import (
    SIGNATURE_HEADER,
    InMemoryReplayGuard,
    ReplayGuard,
    WebhookEvent,
    WebhookRejected,
    secret_for,
    verify_signature,
)

router = APIRouter()

_replay: ReplayGuard = InMemoryReplayGuard()


def get_replay_guard() -> ReplayGuard:
    """Overridable: the app replaces the in-memory guard with a durable one."""
    return _replay


@router.post("/platforms/{platform}", status_code=status.HTTP_202_ACCEPTED, tags=["webhooks"])
async def receive_platform_webhook(
    platform: str,
    request: Request,
    guard: Annotated[ReplayGuard, Depends(get_replay_guard)],
    signature: Annotated[str | None, Header(alias=SIGNATURE_HEADER)] = None,
) -> JSONResponse:
    """Accept one platform event: verify, deduplicate, then hand it to the dispatcher."""
    secret = secret_for(platform)
    if secret is None:
        # Unknown platform or no secret configured: refuse rather than accept unauthenticated events.
        raise Problem(
            404,
            "Unknown platform",
            detail=f"no webhook secret is configured for platform {platform!r}",
            reason="unknown_platform",
        )
    body = await request.body()
    try:
        verify_signature(secret, body, signature)
    except WebhookRejected as exc:
        raise Problem(401, "Invalid signature", detail=exc.detail, reason=exc.reason) from exc
    event = _parse(platform, body)
    if not await guard.first_seen(platform, event.platform_ref):
        # Platforms retry; a duplicate is accepted and ignored, never applied twice.
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "duplicate", "platform_ref": event.platform_ref},
        )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"status": "accepted", "platform_ref": event.platform_ref},
    )


def _parse(platform: str, body: bytes) -> WebhookEvent:
    """The contract's ``PlatformWebhookEvent``. A malformed body is a 422, never a 500."""
    try:
        payload: dict[str, Any] = json.loads(body)
    except ValueError as exc:
        raise Problem(422, "Malformed payload", detail="the body is not JSON") from exc
    missing = [k for k in ("event_type", "platform_ref", "occurred_at") if not payload.get(k)]
    if missing:
        raise Problem(
            422,
            "Malformed payload",
            detail=f"missing required fields: {', '.join(missing)}",
        )
    try:
        occurred_at = datetime.fromisoformat(str(payload["occurred_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise Problem(422, "Malformed payload", detail="occurred_at is not a timestamp") from exc
    return WebhookEvent(
        platform=platform,
        event_type=str(payload["event_type"]),
        platform_ref=str(payload["platform_ref"]),
        occurred_at=occurred_at,
        data=payload.get("data") or {},
    )


__all__ = ["get_replay_guard", "router"]
