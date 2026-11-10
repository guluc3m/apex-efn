"""Access-token verification: one test per way a token can be wrong."""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import timedelta

import jwt
import pytest

from apex.auth.errors import (
    BAD_SIGNATURE,
    EXPIRED,
    MALFORMED,
    MISSING_CLAIM,
    NOT_YET_VALID,
    UNKNOWN_KEY,
    UNSUPPORTED_ALGORITHM,
    WRONG_AUDIENCE,
    WRONG_ISSUER,
    AuthError,
)
from apex.auth.tokens import verify_access_token
from tests.auth.helpers import KID, NOW, b64


async def test_valid_token_becomes_a_verified_token(provider, settings, make_token):
    verified = await verify_access_token(
        make_token(), provider=provider, settings=settings, now=NOW
    )

    assert verified.user_id == "user-1"
    assert verified.tenant_id == "tenant-a"
    assert verified.roles == ("owner",)
    assert verified.auth_time == int((NOW - timedelta(minutes=1)).timestamp())
    assert verified.acr is None
    assert verified.expires_at == NOW + timedelta(minutes=5)
    assert verified.is_signer is True


async def test_step_up_acr_is_exposed(provider, settings, make_token):
    verified = await verify_access_token(
        make_token(claims={"acr": "urn:apex:loa:2"}),
        provider=provider,
        settings=settings,
        now=NOW,
    )

    assert verified.acr == "urn:apex:loa:2"


async def test_roles_are_filtered_to_the_closed_set_in_canonical_order(
    provider, settings, make_token
):
    token = make_token(claims={"roles": ["viewer", "offline_access", "finance", "superuser"]})

    verified = await verify_access_token(token, provider=provider, settings=settings, now=NOW)

    assert verified.roles == ("finance", "viewer")
    assert verified.is_signer is True


async def test_roles_fall_back_to_realm_access_roles(provider, settings, private_pem, base_claims):
    payload = dict(base_claims)
    payload.pop("roles")
    payload["realm_access"] = {"roles": ["admin", "uma_authorization"]}
    token = jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": KID, "typ": "JWT"})

    verified = await verify_access_token(token, provider=provider, settings=settings, now=NOW)

    assert verified.roles == ("admin",)


async def test_claims_are_read_only(provider, settings, make_token):
    verified = await verify_access_token(
        make_token(), provider=provider, settings=settings, now=NOW
    )

    with pytest.raises(TypeError):
        verified.claims["tenant_id"] = "tenant-b"  # type: ignore[index]


@pytest.mark.parametrize(
    ("claims", "reason"),
    [
        ({"exp": int((NOW - timedelta(minutes=5)).timestamp())}, EXPIRED),
        ({"nbf": int((NOW + timedelta(minutes=5)).timestamp())}, NOT_YET_VALID),
        ({"iat": int((NOW + timedelta(minutes=5)).timestamp())}, NOT_YET_VALID),
        ({"iss": "https://other-idp.test/realms/apex"}, WRONG_ISSUER),
        ({"aud": "another-client"}, WRONG_AUDIENCE),
        ({"tenant_id": None}, MISSING_CLAIM),
        ({"tenant_id": "   "}, MALFORMED),
        ({"auth_time": "soon"}, MALFORMED),
        ({"acr": 2}, MALFORMED),
    ],
)
async def test_claim_problems_are_refused_with_a_closed_reason(
    provider, settings, make_token, claims, reason
):
    with pytest.raises(AuthError) as caught:
        await verify_access_token(
            make_token(claims=claims), provider=provider, settings=settings, now=NOW
        )

    assert caught.value.reason == reason


async def test_missing_subject_is_refused(provider, settings, private_pem, base_claims):
    payload = dict(base_claims)
    payload.pop("sub")
    token = jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": KID, "typ": "JWT"})

    with pytest.raises(AuthError) as caught:
        await verify_access_token(token, provider=provider, settings=settings, now=NOW)

    assert caught.value.reason == MISSING_CLAIM


async def test_bad_signature_is_refused(provider, settings, make_token, other_pem):
    with pytest.raises(AuthError) as caught:
        await verify_access_token(
            make_token(key=other_pem), provider=provider, settings=settings, now=NOW
        )

    assert caught.value.reason == BAD_SIGNATURE


async def test_alg_none_is_refused_before_any_signature_check(provider, settings, base_claims):
    token = f"{b64({'alg': 'none', 'typ': 'JWT', 'kid': KID})}.{b64(base_claims)}."

    with pytest.raises(AuthError) as caught:
        await verify_access_token(token, provider=provider, settings=settings, now=NOW)

    assert caught.value.reason == UNSUPPORTED_ALGORITHM


async def test_hs256_signed_with_the_public_key_is_algorithm_confusion_and_is_refused(
    provider, settings, base_claims, public_pem
):
    # PyJWT refuses to *encode* this on purpose, so build the attack by hand: the public key is used as
    # the HMAC secret, which is exactly what a confused verifier would accept.
    header = b64({"alg": "HS256", "typ": "JWT", "kid": KID})
    payload = b64(base_claims)
    signing_input = f"{header}.{payload}"
    signature = (
        base64.urlsafe_b64encode(
            hmac.new(public_pem, signing_input.encode(), hashlib.sha256).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    token = f"{signing_input}.{signature}"

    with pytest.raises(AuthError) as caught:
        await verify_access_token(token, provider=provider, settings=settings, now=NOW)

    assert caught.value.reason == UNSUPPORTED_ALGORITHM


async def test_wrong_typ_is_refused(provider, settings, make_token):
    with pytest.raises(AuthError) as caught:
        await verify_access_token(
            make_token(typ="JWTX"), provider=provider, settings=settings, now=NOW
        )

    assert caught.value.reason == MALFORMED


async def test_unknown_kid_is_refused(provider, settings, make_token):
    with pytest.raises(AuthError) as caught:
        await verify_access_token(
            make_token(kid="rotated-away"), provider=provider, settings=settings, now=NOW
        )

    assert caught.value.reason == UNKNOWN_KEY


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
async def test_malformed_tokens_are_refused(provider, settings, token):
    with pytest.raises(AuthError) as caught:
        await verify_access_token(token, provider=provider, settings=settings, now=NOW)

    assert caught.value.reason == MALFORMED


async def test_error_message_never_contains_the_token(provider, settings, make_token):
    token = make_token(claims={"exp": int((NOW - timedelta(minutes=5)).timestamp())})

    with pytest.raises(AuthError) as caught:
        await verify_access_token(token, provider=provider, settings=settings, now=NOW)

    assert token not in str(caught.value)
    assert token not in repr(caught.value)
