"""JSON Canonicalization Scheme, RFC 8785 (D2-06, ADR-208).

Signed payloads are hashed and signed over ``canonical_bytes(payload)``. The browser does the same with
``@apex/crypto-client``; both pass the shared vectors in ``packages/test-vectors/signing/``, byte for byte.

Accepted values are the JSON data model only: ``None``, ``bool``, ``str``, ``int``, ``float``, ``list``/``tuple``
and ``dict`` with ``str`` keys. Anything else raises ``CanonicalizationError`` instead of being coerced, so a
``Decimal``, a ``datetime`` or an ``Enum`` member must be turned into a string by the payload builder, on purpose.

Numbers follow JSON's IEEE 754 double model (RFC 8785 §3.2.2.3): integers must lie within ±(2^53 - 1), because
a larger one cannot be represented exactly by the browser, and money travels as ``*_minor`` integers well below
that. NaN, infinities and lone surrogates are errors, as RFC 8785 requires.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

MAX_SAFE_INTEGER = 2**53 - 1


class CanonicalizationError(ValueError):
    """The value cannot be represented as canonical JSON."""


def canonicalize(value: object) -> str:
    """The RFC 8785 canonical form of ``value``, as text."""
    parts: list[str] = []
    _write(value, parts, "$")
    return "".join(parts)


def canonical_bytes(value: object) -> bytes:
    """The RFC 8785 canonical form of ``value``, UTF-8 encoded: the exact bytes that are hashed and signed."""
    return canonicalize(value).encode("utf-8")


def payload_hash(value: object) -> str:
    """``SHA-256(canonical_bytes(value))`` as lowercase hex (spec §5.10.2)."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def loads(text: str | bytes) -> Any:
    """Parse JSON the way a browser does before canonicalizing (I-JSON, RFC 7493).

    Integers outside the safe range become doubles, as ``JSON.parse`` would make them. Duplicate member names,
    ``NaN`` and ``Infinity`` are rejected.
    """
    return json.loads(
        text,
        parse_int=_parse_int,
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_members,
    )


def format_number(value: float) -> str:
    """ECMAScript ``Number::toString`` (ECMA-262 §7.1.12.1, with Note 2), which RFC 8785 adopts."""
    if math.isnan(value) or math.isinf(value):
        raise CanonicalizationError(f"{value!r} is not a JSON number")
    if value == 0:
        return "0"
    # repr() is the shortest string that round-trips, choosing the closest candidate on ties (David Gay's
    # dtoa, mode 0): the same digits ECMAScript requires. Only the layout differs.
    _, digits, finite_exponent = Decimal(repr(abs(value))).as_tuple()
    significand = "".join(map(str, digits)).rstrip("0")
    exponent = int(finite_exponent) + len(digits) - len(significand)
    k = len(significand)
    n = exponent + k
    prefix = "-" if value < 0 else ""
    if k <= n <= 21:
        return prefix + significand + "0" * (n - k)
    if 0 < n <= 21:
        return prefix + significand[:n] + "." + significand[n:]
    if -6 < n <= 0:
        return prefix + "0." + "0" * (-n) + significand
    e = n - 1
    mantissa = significand if k == 1 else significand[0] + "." + significand[1:]
    return f"{prefix}{mantissa}e{'+' if e > 0 else '-'}{abs(e)}"


def _write(value: object, out: list[str], path: str) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        if type(value) is not str:
            raise CanonicalizationError(
                f"{path}: {type(value).__name__} is not a JSON value; pass its value"
            )
        out.append(_string(value, path))
    elif isinstance(value, int):
        if type(value) is not int:
            raise CanonicalizationError(
                f"{path}: {type(value).__name__} is not a JSON value; pass its value"
            )
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalizationError(
                f"{path}: integer {value} is outside ±(2^53 - 1); send it as a string"
            )
        out.append(str(value))
    elif isinstance(value, float):
        if type(value) is not float:
            raise CanonicalizationError(
                f"{path}: {type(value).__name__} is not a JSON value; pass its value"
            )
        try:
            out.append(format_number(value))
        except CanonicalizationError as error:
            raise CanonicalizationError(f"{path}: {error}") from None
    elif isinstance(value, Mapping):
        _write_object(value, out, path)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _write(item, out, f"{path}[{index}]")
        out.append("]")
    else:
        raise CanonicalizationError(f"{path}: {type(value).__name__} is not a JSON value")


def _write_object(value: Mapping[Any, Any], out: list[str], path: str) -> None:
    members: list[tuple[bytes, str, str]] = []
    for key in value:
        if type(key) is not str:
            raise CanonicalizationError(f"{path}: object key {key!r} is not a string")
        # RFC 8785 §3.2.3: sort by UTF-16 code units. Big-endian UTF-16 bytes compare in the same order.
        members.append((key.encode("utf-16-be", "surrogatepass"), _string(key, path), key))
    members.sort()
    out.append("{")
    for index, (_, serialized, key) in enumerate(members):
        if index:
            out.append(",")
        out.append(serialized)
        out.append(":")
        _write(value[key], out, f"{path}.{key}")
    out.append("}")


def _string(value: str, path: str) -> str:
    # A str from Python or from json.loads holds valid pairs as one code point, so any surrogate left is lone.
    if any("\ud800" <= ch <= "\udfff" for ch in value):
        raise CanonicalizationError(f"{path}: string contains a lone surrogate")
    return json.dumps(value, ensure_ascii=False)


def _parse_int(text: str) -> int | float:
    number = int(text)
    return number if abs(number) <= MAX_SAFE_INTEGER else float(text)


def _reject_constant(name: str) -> None:
    raise CanonicalizationError(f"{name} is not valid JSON")


def _unique_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise CanonicalizationError(f"duplicate member name {key!r}")
        result[key] = item
    return result


__all__ = [
    "MAX_SAFE_INTEGER",
    "CanonicalizationError",
    "canonical_bytes",
    "canonicalize",
    "format_number",
    "loads",
    "payload_hash",
]
