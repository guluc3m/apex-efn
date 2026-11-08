"""ASGI entry point for uvicorn (``llm_stub.server:app``), configured from the environment."""

from llm_stub.app import create_app

app = create_app()
