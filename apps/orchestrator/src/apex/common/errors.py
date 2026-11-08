"""RFC 9457 problem+json errors (AGENTS.md section 4, DEV-4 -> all).

Every error response of the public API uses ``application/problem+json``. Business code raises
``Problem`` (or uses the helpers below); the handlers installed by ``install_problem_handlers`` map
framework errors to the same shape. Unhandled exceptions become a generic 500: internals are logged
server-side and never leaked to the client.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"
ABOUT_BLANK = "about:blank"

logger = logging.getLogger(__name__)


class ProblemDetails(BaseModel):
    """RFC 9457 problem details. Extension members are allowed (``reason``, ``errors``, ...)."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(default=ABOUT_BLANK)
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class Problem(Exception):
    """Raise to answer with a problem+json body. ``extensions`` become top-level members."""

    def __init__(
        self,
        status: int,
        title: str,
        *,
        detail: str | None = None,
        type_: str = ABOUT_BLANK,
        headers: dict[str, str] | None = None,
        **extensions: Any,
    ) -> None:
        super().__init__(title)
        self.status = status
        self.title = title
        self.detail = detail
        self.type_ = type_
        self.headers = headers
        self.extensions = extensions

    def to_details(self, instance: str | None = None) -> ProblemDetails:
        return ProblemDetails(
            type=self.type_,
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=instance,
            **self.extensions,
        )


def _problem_response(
    details: ProblemDetails, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = details.model_dump(exclude_none=True)
    return JSONResponse(
        status_code=details.status,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


def not_implemented(detail: str | None = None) -> Problem:
    """501 for routes whose owning lane has not implemented them yet."""
    return Problem(
        501,
        "Not Implemented",
        detail=detail or "This endpoint is not implemented yet.",
    )


def reauth_required(reason: str, *, detail: str | None = None) -> Problem:
    """428 when a signing session is missing, expired or revoked (spec §8 / criteria 19-22)."""
    return Problem(
        428,
        "Reauthentication required",
        detail=detail or "A valid signing session is required for this operation.",
        error="reauth_required",
        reason=reason,
    )


def install_problem_handlers(app: FastAPI) -> None:
    """Register exception handlers that render every error as problem+json."""

    @app.exception_handler(Problem)
    async def _problem(request: Request, exc: Problem) -> JSONResponse:
        return _problem_response(exc.to_details(instance=request.url.path), exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        title = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        details = ProblemDetails(
            title=title,
            status=exc.status_code,
            instance=request.url.path,
        )
        return _problem_response(details, _as_headers(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "loc": list(err.get("loc", ())),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        details = ProblemDetails.model_validate(
            {
                "title": "Request validation failed",
                "status": 422,
                "instance": request.url.path,
                "errors": errors,
            }
        )
        return _problem_response(details)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled exception", exc_info=exc)
        details = ProblemDetails(
            title="Internal server error",
            status=500,
            instance=request.url.path,
        )
        return _problem_response(details)


def _as_headers(exc: HTTPException | StarletteHTTPException) -> dict[str, str] | None:
    return dict(exc.headers) if exc.headers else None


__all__ = [
    "PROBLEM_CONTENT_TYPE",
    "Problem",
    "ProblemDetails",
    "install_problem_handlers",
    "not_implemented",
    "reauth_required",
]
