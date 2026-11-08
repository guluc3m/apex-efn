"""APEX-EFN OpenAI-compatible LLM stub.

Public entry points:

* :func:`llm_stub.app.create_app` - build the FastAPI application.
* :mod:`llm_stub.testing` - in-process mounting helpers for pytest (``httpx.ASGITransport``).
"""

from llm_stub.app import create_app

__all__ = ["create_app"]
__version__ = "0.1.0"
