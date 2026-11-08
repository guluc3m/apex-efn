import json
from pathlib import Path
from typing import Any

import pytest

from apex.platform import redaction
from apex.platform.redaction import REDACTED, is_sensitive_key, redact_attributes, redact_value

VECTORS_PATH = (
    Path(__file__).resolve().parents[4] / "docs" / "observability" / "redaction-vectors.json"
)
VECTORS: list[dict[str, Any]] = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_shared_vectors(vector: dict[str, Any]) -> None:
    assert redact_value(vector["input"]) == vector["expected"]


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "Password",
        "DB_PASSWORD",
        "client-secret",
        "apiKey",
        "x-api-key",
        "cookie",
        "set-cookie",
        "privateKey",
        "session_state",
        "cash_balance",
        "value_minor",
        "iban",
        "budget",
        "envelope",
        "payment_term_days",
        "http.request.header.cookie",
    ],
)
def test_sensitive_keys(key: str) -> None:
    assert is_sensitive_key(key)


@pytest.mark.parametrize(
    "key", ["mission_id", "platform", "offer_count", "signature_status", "tokens", "metric"]
)
def test_non_sensitive_keys(key: str) -> None:
    assert not is_sensitive_key(key)


def test_tuples_and_sets_keep_their_type() -> None:
    assert redact_value(("password=abc", 1)) == ("password=[REDACTED]", 1)


def test_exceptions_keep_type_and_redact_message() -> None:
    result = redact_value(RuntimeError("login failed: token=abc123"))
    assert result["type"] == "RuntimeError"
    assert result["message"] == "login failed: token=[REDACTED]"
    assert "token=[REDACTED]" in result["stack"]


def test_too_deep_structures_fail_closed() -> None:
    nested: dict[str, Any] = {}
    cursor = nested
    for _ in range(redaction.MAX_DEPTH + 5):
        cursor["child"] = {}
        cursor = cursor["child"]
    before = redaction.stats.errors
    result = redact_value(nested)
    assert REDACTED in json.dumps(result)
    assert redaction.stats.errors > before


def test_redact_attributes_returns_a_copy() -> None:
    original = {"authorization": "Bearer abc", "mission_id": "m1"}
    assert redact_attributes(original) == {"authorization": REDACTED, "mission_id": "m1"}
    assert original["authorization"] == "Bearer abc"
