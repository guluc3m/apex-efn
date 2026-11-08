"""RFC 9457 handlers: Problem, HTTP errors, validation (422), reauth_required (428), no leaks (500)."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from apex.common.errors import (
    PROBLEM_CONTENT_TYPE,
    Problem,
    install_problem_handlers,
    not_implemented,
    reauth_required,
)


class Body(BaseModel):
    amount: int


def _app() -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)

    @app.get("/problem")
    async def problem() -> None:
        raise Problem(409, "Conflict", detail="already there", code="dup")

    @app.get("/reauth")
    async def reauth() -> None:
        raise reauth_required("session_expired")

    @app.get("/http")
    async def http_error() -> None:
        raise HTTPException(status_code=404, detail="no such thing", headers={"X-A": "1"})

    @app.get("/boom")
    async def boom() -> None:
        raise ValueError("db password=hunter2")

    @app.post("/body")
    async def body(payload: Body) -> dict[str, int]:
        return {"amount": payload.amount}

    @app.get("/ni")
    async def ni() -> None:
        raise not_implemented()

    return app


def test_problem_renders_rfc9457_with_extensions() -> None:
    response = TestClient(_app()).get("/problem")
    assert response.status_code == 409
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body == {
        "type": "about:blank",
        "title": "Conflict",
        "status": 409,
        "detail": "already there",
        "instance": "/problem",
        "code": "dup",
    }


def test_reauth_required_is_428_with_reason() -> None:
    response = TestClient(_app()).get("/reauth")
    assert response.status_code == 428
    body = response.json()
    assert body["error"] == "reauth_required"
    assert body["reason"] == "session_expired"


def test_http_exception_is_problem_json_and_keeps_headers() -> None:
    response = TestClient(_app()).get("/http")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert response.headers["x-a"] == "1"
    assert response.json()["title"] == "no such thing"


def test_validation_error_is_422_problem_json() -> None:
    response = TestClient(_app()).post("/body", json={"amount": "not-a-number"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["title"] == "Request validation failed"
    assert body["errors"][0]["loc"] == ["body", "amount"]


def test_unhandled_exception_is_500_without_internals() -> None:
    response = TestClient(_app(), raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert "hunter2" not in response.text
    assert response.json()["title"] == "Internal server error"


def test_not_implemented_helper() -> None:
    response = TestClient(_app()).get("/ni")
    assert response.status_code == 501
    assert response.json()["title"] == "Not Implemented"
