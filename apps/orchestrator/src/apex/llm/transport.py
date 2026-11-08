"""Thin HTTP transport speaking only the OpenAI-compatible contract (spec §5.6).

Only three paths are used: ``POST /v1/chat/completions``, ``POST /v1/embeddings``, ``GET /v1/models``.
No vendor SDK. Injectable ``httpx.AsyncClient`` / ``httpx.AsyncBaseTransport`` for tests. The API key is
attached per request and never stored on the transport's public surface, logged, or put in errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr


class LLMHTTPError(Exception):
    """Non-2xx response from an endpoint. Carries status and Retry-After, never the auth header."""

    def __init__(
        self,
        status_code: int,
        body_excerpt: str,
        *,
        retry_after_s: float | None = None,
        endpoint_id: str = "",
    ) -> None:
        self.status_code = status_code
        self.body_excerpt = body_excerpt
        self.retry_after_s = retry_after_s
        self.endpoint_id = endpoint_id
        super().__init__(f"endpoint {endpoint_id or '?'} returned HTTP {status_code}")

    @property
    def is_unsupported(self) -> bool:
        """HTTP 400 that signals an unsupported feature (e.g. json_schema not supported)."""
        if self.status_code != 400:
            return False
        lowered = self.body_excerpt.lower()
        return any(
            marker in lowered
            for marker in ("unsupported", "not supported", "not_supported", "unknown parameter")
        )

    @property
    def is_retryable(self) -> bool:
        return self.status_code in (408, 425, 429) or self.status_code >= 500


class LLMTransportError(Exception):
    """Network-level failure (timeout, connection reset) — always retryable."""

    def __init__(self, endpoint_id: str, reason: str) -> None:
        self.endpoint_id = endpoint_id
        self.reason = reason
        super().__init__(f"transport failure on endpoint {endpoint_id or '?'}: {reason}")


def normalise_base_url(base_url: str) -> str:
    """Return the root (scheme://host[/prefix]) with any trailing ``/v1`` and slashes removed."""
    root = base_url.strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return root.rstrip("/")


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


@dataclass(frozen=True)
class RawResponse:
    status_code: int
    json: dict[str, Any]


class OpenAICompatTransport:
    """Speaks the three OpenAI-compatible paths against one endpoint."""

    def __init__(
        self,
        *,
        endpoint_id: str,
        base_url: str,
        timeout_s: float,
        api_key: SecretStr | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint_id = endpoint_id
        self._root = normalise_base_url(base_url)
        self._api_key = api_key
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout_s)
        self._timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key.get_secret_value()}"
        return headers

    async def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None
    ) -> RawResponse:
        url = f"{self._root}{path}"
        try:
            response = await self._client.request(
                method,
                url,
                json=json_body,
                headers=self._headers(),
                timeout=self._timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise LLMTransportError(self._endpoint_id, "timeout") from exc
        except httpx.TransportError as exc:
            raise LLMTransportError(self._endpoint_id, type(exc).__name__) from exc

        if response.status_code >= 400:
            raise LLMHTTPError(
                response.status_code,
                response.text[:300],
                retry_after_s=_parse_retry_after(response.headers.get("Retry-After")),
                endpoint_id=self._endpoint_id,
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMHTTPError(
                response.status_code,
                "non-JSON response body",
                endpoint_id=self._endpoint_id,
            ) from exc
        return RawResponse(status_code=response.status_code, json=body)

    async def chat_completions(self, payload: dict[str, Any]) -> RawResponse:
        return await self._request("POST", "/v1/chat/completions", payload)

    async def embeddings(self, payload: dict[str, Any]) -> RawResponse:
        return await self._request("POST", "/v1/embeddings", payload)

    async def list_models(self) -> RawResponse:
        return await self._request("GET", "/v1/models", None)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = [
    "LLMHTTPError",
    "LLMTransportError",
    "OpenAICompatTransport",
    "RawResponse",
    "normalise_base_url",
]
