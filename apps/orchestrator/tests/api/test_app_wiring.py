"""App shell wiring: problem handlers and /health."""

from fastapi.testclient import TestClient

from apex.config import Settings
from apex.main import create_app


def test_health_is_unversioned_and_ok() -> None:
    response = TestClient(create_app(Settings())).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_unknown_route_is_problem_json_404() -> None:
    response = TestClient(create_app(Settings())).get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
