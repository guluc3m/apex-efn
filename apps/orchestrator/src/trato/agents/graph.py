"""Mission graph definition using LangGraph.

Implements the agent flow from section 4:
discovered -> enriched -> trust_scored -> sanity_checked -> (gate) ->
financially_checked -> negotiating -> negotiated -> sanity_rechecked ->
scored -> awaiting_human -> signed -> approved | rejected -> purchased
"""

from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from trato.agents.state import MissionState


def create_mission_graph() -> CompiledStateGraph[MissionState, None, MissionState, MissionState]:
    """Create the mission orchestration graph.

    This is a scaffold - actual agent implementations will be added
    in subsequent phases.
    """
    graph = StateGraph(MissionState)

    # Node stubs - to be implemented
    async def plan(state: MissionState) -> dict[str, Any]:
        """PlannerAgent: decide sources, queries, budget."""
        return {"status": "planning_complete"}

    async def source(state: MissionState) -> dict[str, Any]:
        """ScraperAgent: extract offers from platforms."""
        return {"status": "sourcing_complete"}

    async def enrich(state: MissionState) -> dict[str, Any]:
        """EnrichmentAgent: normalize, dedupe, translate."""
        return {"status": "enrichment_complete"}

    async def score_trust(state: MissionState) -> dict[str, Any]:
        """TrustAgent: compute seller confidence."""
        return {"status": "trust_scored"}

    async def check_sanity(state: MissionState) -> dict[str, Any]:
        """SanityAgent: check price bands."""
        return {"status": "sanity_checked"}

    async def check_gate(state: MissionState) -> dict[str, Any]:
        """GateAgent: combine price and confidence, route to gate if needed."""
        return {"needs_gate": False}

    async def await_gate(state: MissionState) -> dict[str, Any]:
        """Wait for human decision on gated items."""
        return {"gate_resolved": True}

    async def check_financial(state: MissionState) -> dict[str, Any]:
        """FinanceAgent: compute landed cost, check budget."""
        return {"status": "financially_checked"}

    async def negotiate(state: MissionState) -> dict[str, Any]:
        """NegotiatorAgent: conduct negotiation."""
        return {"status": "negotiated"}

    async def recheck_sanity(state: MissionState) -> dict[str, Any]:
        """Re-check price after negotiation."""
        return {"status": "sanity_rechecked"}

    async def score_offers(state: MissionState) -> dict[str, Any]:
        """EvaluatorAgent: MCDA scoring."""
        return {"status": "scored"}

    async def await_human(state: MissionState) -> dict[str, Any]:
        """Present to human for final decision."""
        return {"status": "awaiting_decision"}

    # Add nodes
    graph.add_node("plan", plan)
    graph.add_node("source", source)
    graph.add_node("enrich", enrich)
    graph.add_node("score_trust", score_trust)
    graph.add_node("check_sanity", check_sanity)
    graph.add_node("check_gate", check_gate)
    graph.add_node("await_gate", await_gate)
    graph.add_node("check_financial", check_financial)
    graph.add_node("negotiate", negotiate)
    graph.add_node("recheck_sanity", recheck_sanity)
    graph.add_node("score_offers", score_offers)
    graph.add_node("await_human", await_human)

    # Define edges
    graph.set_entry_point("plan")
    graph.add_edge("plan", "source")
    graph.add_edge("source", "enrich")
    graph.add_edge("enrich", "score_trust")
    graph.add_edge("score_trust", "check_sanity")
    graph.add_edge("check_sanity", "check_gate")

    # Conditional: gate or proceed
    def route_gate(state: MissionState) -> str:
        if state.get("needs_gate"):
            return "await_gate"
        return "check_financial"

    graph.add_conditional_edges("check_gate", route_gate)
    graph.add_edge("await_gate", "check_financial")

    graph.add_edge("check_financial", "negotiate")
    graph.add_edge("negotiate", "recheck_sanity")
    graph.add_edge("recheck_sanity", "score_offers")
    graph.add_edge("score_offers", "await_human")
    graph.add_edge("await_human", END)

    return graph.compile()
