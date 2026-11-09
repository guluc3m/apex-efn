"""Ed25519 verification of signed payloads (D2-06, ADR-208).

The signed message is ``jcs.canonical_bytes(payload)``. Public keys are the raw 32 bytes and signatures the raw
64 bytes, both as standard padded Base64 on the wire (``contracts/openapi.yaml``). Human private keys never reach
the server; service keys sign inside Vault Transit (D2-07). This module only verifies.
"""

from __future__ import annotations

import base64
import binascii

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from apex.signing.jcs import canonical_bytes

PUBLIC_KEY_BYTES = 32
SIGNATURE_BYTES = 64


class MalformedKeyOrSignature(ValueError):
    """A public key or signature that is not valid Base64 or has the wrong length."""


def decode_base64(value: str, length: int, what: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise MalformedKeyOrSignature(f"{what} is not standard Base64") from error
    if len(raw) != length:
        raise MalformedKeyOrSignature(f"{what} must be {length} bytes, got {len(raw)}")
    if base64.b64encode(raw).decode("ascii") != value:
        raise MalformedKeyOrSignature(f"{what} is not in canonical padded Base64")
    return raw


def load_public_key(public_key_b64: str) -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(
        decode_base64(public_key_b64, PUBLIC_KEY_BYTES, "public key")
    )


def verify_bytes(public_key_b64: str, signature_b64: str, message: bytes) -> bool:
    """True when ``signature_b64`` is a valid Ed25519 signature of ``message`` by ``public_key_b64``."""
    key = load_public_key(public_key_b64)
    signature = decode_base64(signature_b64, SIGNATURE_BYTES, "signature")
    try:
        key.verify(signature, message)
    except InvalidSignature:
        return False
    return True


def verify_payload(public_key_b64: str, signature_b64: str, payload: object) -> bool:
    """Verify a signature over the RFC 8785 canonical bytes of ``payload``."""
    return verify_bytes(public_key_b64, signature_b64, canonical_bytes(payload))


__all__ = [
    "PUBLIC_KEY_BYTES",
    "SIGNATURE_BYTES",
    "MalformedKeyOrSignature",
    "decode_base64",
    "load_public_key",
    "verify_bytes",
    "verify_payload",
]
