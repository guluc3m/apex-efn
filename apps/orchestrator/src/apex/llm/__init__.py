"""LLM Gateway — OpenAI-compatible HTTP access for every agent role (spec §5.6).

Only ``/v1/chat/completions``, ``/v1/embeddings`` and ``/v1/models`` are used. No proprietary SDKs.
"""

from apex.llm.config import (
    CapabilityProfile,
    GuidedDecoding,
    LLMRole,
    LLMRolesConfig,
    RoleEndpointConfig,
)
from apex.llm.structured import StructuredOutputError

__all__ = [
    "CapabilityProfile",
    "GuidedDecoding",
    "LLMRole",
    "LLMRolesConfig",
    "RoleEndpointConfig",
    "StructuredOutputError",
]
