"""The orchestrator's HTTP surface and contracts/openapi.yaml must list the same operations (D2-01).

The contract is the source of truth (spec 5.1). A route added to FastAPI without a contract PR, or a
contract path nobody serves, fails here instead of surfacing as a broken client later.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI

from apex.config import Settings
from apex.contracts.generated import models
from apex.main import create_app

CONTRACT = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "head", "options", "trace"})


def _operations(paths: dict[str, Any]) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path, item in paths.items():
        if not path.startswith("/v1/"):
            continue
        for method in item:
            if method in HTTP_METHODS:
                found.add((method.upper(), path))
    return found


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    with CONTRACT.open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = yaml.safe_load(handle)
    return loaded


@pytest.fixture(scope="module")
def app() -> FastAPI:
    return create_app(Settings(idempotency_backend="memory"))


def test_served_routes_match_contract(contract: dict[str, Any], app: FastAPI) -> None:
    served = _operations(app.openapi()["paths"])
    declared = _operations(contract["paths"])
    assert sorted(served - declared) == [], "served but missing from contracts/openapi.yaml"
    assert sorted(declared - served) == [], "in contracts/openapi.yaml but not served"


def test_every_contract_operation_has_an_operation_id(contract: dict[str, Any]) -> None:
    missing = [
        (method.upper(), path)
        for path, item in contract["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS and not operation.get("operationId")
    ]
    assert missing == []


def test_generated_models_keep_money_and_currency_rules() -> None:
    assert {member.value for member in models.Currency} == {"EUR", "USD", "CNY"}
    money = models.Money(amount_minor=2_100_000_000_00, currency=models.Currency.EUR)
    assert money.amount_minor == 2_100_000_000_00
    with pytest.raises(ValueError):
        models.Money.model_validate({"amount_minor": 1.5, "currency": "EUR"})
    with pytest.raises(ValueError):
        models.Money.model_validate({"amount_minor": 100, "currency": "GBP"})
