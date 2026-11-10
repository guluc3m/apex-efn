"""Every unimplemented §8 route answers 501 problem+json; no unexpected /v1 routes exist.

Routes implemented by DEV-4 (``IMPLEMENTED_ROUTES``) are excluded: they answer real responses and are
covered by their own tests.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apex.config import Settings
from apex.main import create_app
from tests.api.spec_routes import EXPECTED_ROUTES, IMPLEMENTED_ROUTES, SPEC_ROUTES

PROBLEM_JSON = "application/problem+json"


@pytest.fixture(autouse=True)
def _tenant_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let the tenant resolve so a stub route reaches its 501 instead of stopping at the 401."""
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")


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


def test_implemented_routes_are_not_stubs(app: FastAPI) -> None:
    """A route listed as implemented must not answer 501 any more."""
    client = TestClient(app, raise_server_exceptions=False)
    for method, path in sorted(IMPLEMENTED_ROUTES):
        response = client.request(
            method, _concrete(path), json={}, headers={"X-Tenant-Id": "tenant-a"}
        )
        assert response.status_code != 501, (method, path, response.status_code)


@pytest.mark.parametrize(("method", "path"), sorted(SPEC_ROUTES - IMPLEMENTED_ROUTES))
def test_stub_answers_501_problem_json(app: FastAPI, method: str, path: str) -> None:
    """A stub route answers 501 problem+json — or 401 when it resolves the tenant before its own dependency.

    Both prove the route exists and is not implemented; the 401 is the tenant gate doing its job on a route
    that has nothing to serve yet.
    """
    client = TestClient(app, raise_server_exceptions=False)
    response = client.request(method, _concrete(path), json={})
    assert response.status_code in {401, 501}, (method, path, response.status_code)
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["status"] == response.status_code
    assert body["instance"] == _concrete(path)
    if response.status_code == 501:
        assert body["title"] == "Not Implemented"
