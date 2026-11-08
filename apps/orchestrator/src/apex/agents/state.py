"""Mission state for LangGraph."""

from typing import Any, TypedDict


class MissionState(TypedDict, total=False):
    """State passed through the mission graph.

    This is extended as agents add data.
    """

    # Mission metadata
    mission_id: str
    tenant_id: str
    request_id: str

    # Status tracking
    status: str
    error: str | None

    # Planning
    plan: dict[str, Any] | None
    platforms: list[str]
    queries: list[dict[str, Any]]

    # Offers
    offers_raw: list[dict[str, Any]]
    offers_enriched: list[dict[str, Any]]
    offers_scored: list[dict[str, Any]]

    # Gate
    needs_gate: bool
    gate_items: list[dict[str, Any]]
    gate_resolved: bool

    # Negotiation
    negotiations: list[dict[str, Any]]

    # Final
    recommendations: list[dict[str, Any]]

    # Tokens
    tokens_used: int
    token_budget: int
