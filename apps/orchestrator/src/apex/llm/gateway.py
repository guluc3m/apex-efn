"""LLM Gateway - OpenAI-compatible HTTP client.

Implements section 5.6 of the spec:
- Only uses /v1/chat/completions, /v1/embeddings, /v1/models
- No proprietary endpoints
- Supports base_url override for self-hosted models
- Capability profiles per endpoint
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from apex.config import settings


class LLMRole(StrEnum):
    """LLM roles with different model configurations."""

    PLANNER = "planner"
    NEGOTIATOR = "negotiator"
    EXTRACTOR = "extractor"
    NARRATOR = "narrator"
    EMBEDDER = "embedder"


@dataclass
class EndpointCapabilities:
    """Declared capabilities of an LLM endpoint."""

    supports_json_schema: bool = False
    supports_tools: bool = False
    supports_streaming: bool = True
    supports_seed: bool = False
    context_window: int = 4096
    tokenizer: str = "cl100k_base"


@dataclass
class ChatMessage:
    """Chat message format."""

    role: str
    content: str


@dataclass
class ChatCompletion:
    """Chat completion response."""

    content: str
    model: str
    tokens_prompt: int
    tokens_completion: int
    finish_reason: str


class LLMGateway:
    """OpenAI-compatible LLM gateway.

    All model access goes through this class.
    Only uses standard OpenAI API endpoints.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ):
        self.base_url = (base_url or settings.llm_gateway_url).rstrip("/")
        self.api_key = api_key or settings.llm_gateway_api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        return self._client

    def _get_model_for_role(self, role: LLMRole) -> str:
        """Get configured model for a role."""
        model_map = {
            LLMRole.PLANNER: settings.llm_planner_model,
            LLMRole.NEGOTIATOR: settings.llm_negotiator_model,
            LLMRole.EXTRACTOR: settings.llm_extractor_model,
            LLMRole.NARRATOR: settings.llm_narrator_model,
            LLMRole.EMBEDDER: settings.llm_embedder_model,
        }
        return model_map[role]

    async def chat(
        self,
        messages: list[ChatMessage],
        role: LLMRole,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        seed: int | None = None,
    ) -> ChatCompletion:
        """Send chat completion request.

        Uses only POST /v1/chat/completions - standard OpenAI endpoint.
        """
        client = await self._get_client()
        model = self._get_model_for_role(role)

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        if response_format:
            payload["response_format"] = response_format

        if seed is not None:
            payload["seed"] = seed

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()

        data = response.json()
        choice = data["choices"][0]

        return ChatCompletion(
            content=choice["message"]["content"],
            model=data["model"],
            tokens_prompt=data["usage"]["prompt_tokens"],
            tokens_completion=data["usage"]["completion_tokens"],
            finish_reason=choice["finish_reason"],
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings.

        Uses only POST /v1/embeddings - standard OpenAI endpoint.
        """
        client = await self._get_client()
        model = self._get_model_for_role(LLMRole.EMBEDDER)

        response = await client.post(
            "/embeddings",
            json={"model": model, "input": texts},
        )
        response.raise_for_status()

        data = response.json()
        return [item["embedding"] for item in data["data"]]

    async def list_models(self) -> list[str]:
        """List available models.

        Uses only GET /v1/models - standard OpenAI endpoint.
        """
        client = await self._get_client()
        response = await client.get("/models")
        response.raise_for_status()

        data = response.json()
        return [model["id"] for model in data["data"]]

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
