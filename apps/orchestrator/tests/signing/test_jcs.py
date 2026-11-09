"""RFC 8785 canonicalization and Ed25519 helpers: input rules and properties (D2-06, ADR-208)."""

from __future__ import annotations

import base64
import math
from collections import OrderedDict
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum, IntEnum, StrEnum
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import given, settings
from hypothesis import strategies as st

from apex.signing import jcs
from apex.signing.ed25519 import (
    MalformedKeyOrSignature,
    decode_base64,
    verify_bytes,
    verify_payload,
)


class Colour(Enum):
    RED = "red"


class Band(StrEnum):
    HIGH = "high"


class Level(IntEnum):
    ONE = 1


# --- accepted input ----------------------------------------------------------------------------------------------


def test_tuples_and_mappings_are_arrays_and_objects() -> None:
    value = OrderedDict([("b", (1, 2)), ("a", [True, None])])
    assert jcs.canonicalize(value) == '{"a":[true,null],"b":[1,2]}'


def test_integers_and_integral_floats_serialize_alike() -> None:
    assert jcs.canonicalize([1, 1.0, -0.0, 0]) == "[1,1,0,0]"


def test_safe_integer_bounds() -> None:
    assert jcs.canonicalize(jcs.MAX_SAFE_INTEGER) == "9007199254740991"
    assert jcs.canonicalize(-jcs.MAX_SAFE_INTEGER) == "-9007199254740991"
    for too_big in (jcs.MAX_SAFE_INTEGER + 1, -jcs.MAX_SAFE_INTEGER - 1, 2**63):
        with pytest.raises(jcs.CanonicalizationError, match="outside"):
            jcs.canonicalize({"amount_minor": too_big})


def test_payload_hash_is_sha256_hex_of_the_canonical_bytes() -> None:
    assert (
        jcs.payload_hash({}) == "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
    )
    assert jcs.payload_hash({"b": 1, "a": 2}) == jcs.payload_hash({"a": 2, "b": 1})


# --- rejected input ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        Decimal("1.5"),
        datetime(2026, 1, 1, tzinfo=UTC),
        Colour.RED,
        Band.HIGH,
        Level.ONE,
        b"bytes",
        bytearray(b"x"),
        {1, 2},
        object(),
        {1: "integer key"},
        {Band.HIGH: "enum key"},
        float("nan"),
        float("inf"),
        float("-inf"),
        "lone \ud800",
    ],
    ids=repr,
)
def test_non_json_values_are_rejected(value: object) -> None:
    with pytest.raises(jcs.CanonicalizationError):
        jcs.canonicalize(value)


def test_errors_name_the_path() -> None:
    with pytest.raises(jcs.CanonicalizationError, match=r"^\$\.offer\.prices\[1\]: Decimal"):
        jcs.canonicalize({"offer": {"prices": [1, Decimal("2")]}})


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"a":1,"a":2}', "duplicate member"),
        ("[NaN]", "NaN"),
        ("[Infinity]", "Infinity"),
        ("[-Infinity]", "Infinity"),
    ],
)
def test_loads_rejects_what_i_json_forbids(text: str, message: str) -> None:
    with pytest.raises(jcs.CanonicalizationError, match=message):
        jcs.loads(text)


def test_loads_turns_unsafe_integers_into_doubles_like_json_parse() -> None:
    assert jcs.loads("[9007199254740991, 9007199254740993]") == [
        9007199254740991,
        9007199254740992.0,
    ]
    assert type(jcs.loads("9007199254740993")) is float


# --- properties --------------------------------------------------------------------------------------------------

_text = st.text(st.characters(exclude_categories=("Cs",)))
_scalar = (
    st.none()
    | st.booleans()
    | st.integers(-jcs.MAX_SAFE_INTEGER, jcs.MAX_SAFE_INTEGER)
    | st.floats(allow_nan=False, allow_infinity=False)
    | _text
)
_json = st.recursive(
    _scalar,
    lambda children: st.lists(children, max_size=5) | st.dictionaries(_text, children, max_size=5),
    max_leaves=30,
)


@settings(max_examples=400)
@given(_json)
def test_canonical_form_is_a_fixed_point(value: Any) -> None:
    canonical = jcs.canonicalize(value)
    assert jcs.canonicalize(jcs.loads(canonical)) == canonical


@settings(max_examples=400)
@given(st.dictionaries(_text, _scalar, max_size=8))
def test_member_order_does_not_matter(value: dict[str, Any]) -> None:
    reversed_value = dict(reversed(list(value.items())))
    assert jcs.canonicalize(reversed_value) == jcs.canonicalize(value)


@settings(max_examples=2000)
@given(st.floats(allow_nan=False, allow_infinity=False))
def test_numbers_round_trip_exactly(value: float) -> None:
    text = jcs.format_number(value)
    parsed = float(text)
    assert parsed == value
    assert math.copysign(1, parsed) == math.copysign(1, value) or value == 0


# --- Ed25519 helpers ---------------------------------------------------------------------------------------------

SECRET = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
KEY = Ed25519PrivateKey.from_private_bytes(SECRET)
PUBLIC = base64.b64encode(
    KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
).decode()


def _sign(payload: object) -> str:
    return base64.b64encode(KEY.sign(jcs.canonical_bytes(payload))).decode()


def test_changing_the_score_in_a_signed_payload_fails_verification() -> None:
    payload = {
        "seller_confidence": {"score": 78, "band": "high"},
        "amount": {"amount_minor": 1250000},
    }
    signature = _sign(payload)
    assert verify_payload(PUBLIC, signature, payload)
    assert verify_payload(PUBLIC, signature, {**payload})
    assert not verify_payload(
        PUBLIC, signature, {**payload, "seller_confidence": {"score": 79, "band": "high"}}
    )
    assert not verify_payload(PUBLIC, signature, {**payload, "amount": {"amount_minor": 1250001}})


def test_a_different_key_does_not_verify() -> None:
    other = Ed25519PrivateKey.generate().public_key()
    other_b64 = base64.b64encode(
        other.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    assert not verify_payload(other_b64, _sign({"a": 1}), {"a": 1})


@pytest.mark.parametrize(
    "value",
    [
        "not base64!",
        base64.b64encode(b"\x00" * 31).decode(),
        base64.b64encode(b"\x00" * 33).decode(),
        base64.b64encode(b"\x00" * 32).decode().rstrip("="),
        base64.urlsafe_b64encode(b"\xff" * 32).decode(),
        " " + base64.b64encode(b"\x00" * 32).decode(),
        "A" * 42 + "B=",  # same 32 bytes with non-zero padding bits: not canonical
    ],
)
def test_public_keys_must_be_canonical_padded_base64_of_32_bytes(value: str) -> None:
    with pytest.raises(MalformedKeyOrSignature):
        decode_base64(value, 32, "public key")


def test_malformed_signature_raises_instead_of_returning_false() -> None:
    with pytest.raises(MalformedKeyOrSignature, match="64 bytes"):
        verify_bytes(PUBLIC, base64.b64encode(b"\x00" * 63).decode(), b"")
