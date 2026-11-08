"""LLM Gateway - OpenAI-compatible HTTP client.

All LLM access goes through this module.
No proprietary SDK dependencies allowed.
"""

from trato.llm.gateway import LLMGateway, LLMRole
from trato.llm.structured import StructuredOutputParser

__all__ = ["LLMGateway", "LLMRole", "StructuredOutputParser"]
