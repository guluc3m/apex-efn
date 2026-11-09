"""Shared signing vectors in ``packages/test-vectors/signing/`` (D2-06, ADR-208).

``@apex/crypto-client`` runs the same files, so passing here and there means TS and Python agree byte for byte.
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apex.signing import jcs
from apex.signing.ed25519 import verify_bytes, verify_payload

VECTORS = Path(__file__).resolve().parents[4] / "packages" / "test-vectors" / "signing"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((VECTORS / name).read_text(encoding="utf-8"))
    return data


def _cases(name: str, key: str = "vectors") -> list[Any]:
    return [pytest.param(case, id=case["name"]) for case in _load(name).get(key, [])]


def _double(hex_bits: str) -> float:
    value: float = struct.unpack(">d", bytes.fromhex(hex_bits))[0]
    return value


def _raw_public_key(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def test_vector_files_are_present() -> None:
    for name in ("jcs.json", "jcs-numbers.json", "ed25519.json", "signatures.json"):
        assert _load(name)["vectors"], name


@pytest.mark.parametrize("case", _cases("jcs.json"))
def test_jcs(case: dict[str, Any]) -> None:
    expected = case["expected"]
    canonical = jcs.canonicalize(jcs.loads(case["input"]))
    assert canonical == expected["canonical"]
    data = jcs.canonical_bytes(jcs.loads(case["input"]))
    assert hashlib.sha256(data).hexdigest() == expected["sha256"]
    if "utf8_hex" in expected:
        assert data.hex() == expected["utf8_hex"]


@pytest.mark.parametrize("case", _cases("jcs.json", "errors"))
def test_jcs_rejects(case: dict[str, Any]) -> None:
    assert case["expected"]["error"] == "lone_surrogate"
    with pytest.raises(jcs.CanonicalizationError, match="lone surrogate"):
        jcs.canonicalize(jcs.loads(case["input"]))


def test_jcs_numbers() -> None:
    # One test for 2,000+ vectors keeps the report readable; the failure lists every mismatch.
    vectors = _load("jcs-numbers.json")["vectors"]
    mismatches = [
        (case["name"], got, case["expected"]["canonical"])
        for case in vectors
        if (got := jcs.canonicalize(_double(case["input"]["ieee754"])))
        != case["expected"]["canonical"]
    ]
    assert mismatches == []
    assert len(vectors) > 2000


@pytest.mark.parametrize("case", _cases("jcs-numbers.json", "errors"))
def test_jcs_numbers_reject_non_finite(case: dict[str, Any]) -> None:
    assert case["expected"]["error"] == "not_finite"
    with pytest.raises(jcs.CanonicalizationError):
        jcs.canonicalize(_double(case["input"]["ieee754"]))


@pytest.mark.parametrize("case", _cases("ed25519.json"))
def test_ed25519_known_answers(case: dict[str, Any]) -> None:
    given = case["input"]
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(given["secret_key"]))
    message = bytes.fromhex(given["message"])
    signature = key.sign(message)
    assert _raw_public_key(key).hex() == given["public_key"]
    assert signature.hex() == case["expected"]["signature"]
    public_b64 = base64.b64encode(bytes.fromhex(given["public_key"])).decode()
    assert verify_bytes(public_b64, base64.b64encode(signature).decode(), message)
    assert not verify_bytes(public_b64, base64.b64encode(signature).decode(), message + b"\x00")


@pytest.mark.parametrize("case", _cases("signatures.json"))
def test_signed_payloads(case: dict[str, Any]) -> None:
    given, expected = case["input"], case["expected"]
    payload = jcs.loads(given["payload"])
    data = jcs.canonical_bytes(payload)
    assert data.decode("utf-8") == expected["canonical"]
    assert jcs.payload_hash(payload) == expected["payload_hash"]

    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(given["secret_key"]))
    assert base64.b64encode(_raw_public_key(key)).decode() == given["public_key"]
    assert base64.b64encode(key.sign(data)).decode() == expected["signature"]
    assert verify_payload(given["public_key"], expected["signature"], payload)

    # Flipping any single byte of the signed message breaks the signature.
    for index in range(0, len(data), max(1, len(data) // 16)):
        tampered = bytearray(data)
        tampered[index] ^= 0x01
        assert not verify_bytes(given["public_key"], expected["signature"], bytes(tampered))
