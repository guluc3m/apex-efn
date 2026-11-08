"""Every §8 route answers 501 problem+json; no unexpected /v1 routes exist."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.config import Settings
from apex.main import create_app
from tests.api.spec_routes import EXPECTED_ROUTES, SPEC_ROUTES

PROBLEM_JSON = "application/problem+json"


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(idempotency_backend="memory"))


def _concrete(path: str) -> str:
    return path.replace("{id}", "t-123").replace("{platform}", "mock-a")


def _v1_routes(app: FastAPI) -> set[tuple[str, str]]:
    # OpenAPI is the public surface and flattens included routers (FastAPI >= 0.115 nests them).
    found: set[tuple[str, str]] = set()
    for path, operations in app.openapi()["paths"].items():
        if not path.startswith("/v1/"):
            continue
        for method in operations:
            found.add((method.upper(), path))
    return found


def test_spec_table_has_all_routes() -> None:
    # 30 operations in spec section 8 (keys/me counts GET and POST separately).
    assert len(SPEC_ROUTES) == 30


def test_route_set_matches_expected_exactly(app: FastAPI) -> None:
    assert _v1_routes(app) == EXPECTED_ROUTES


@pytest.mark.parametrize(("method", "path"), sorted(SPEC_ROUTES))
def test_stub_answers_501_problem_json(app: FastAPI, method: str, path: str) -> None:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.request(method, _concrete(path), json={})
    assert response.status_code == 501, (method, path)
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["status"] == 501
    assert body["title"] == "Not Implemented"
    assert body["instance"] == _concrete(path)
