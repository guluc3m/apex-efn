"""LLM Gateway - OpenAI-compatible HTTP client.

All LLM access goes through this module.
No proprietary SDK dependencies allowed.
"""

from apex.llm.gateway import LLMGateway, LLMRole
from apex.llm.structured import StructuredOutputParser

__all__ = ["LLMGateway", "LLMRole", "StructuredOutputParser"]
