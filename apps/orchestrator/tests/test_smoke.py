from fastapi.testclient import TestClient

from apex.agents.graph import create_mission_graph
from apex.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


async def test_mission_graph_stops_at_human_decision() -> None:
    result = await create_mission_graph().ainvoke({"mission_id": "m1"})
    assert result["status"] == "awaiting_decision"
