"""The FastAPI dependencies: bearer verification, the dev escape hatch and role gating."""

from __future__ import annotations

import pytest

from apex.auth.deps import current_principal, require_role, require_signer
from apex.auth.models import Principal
from apex.auth.settings import AuthSettings
from apex.common.errors import Problem
from tests.auth.helpers import AUDIENCE, ISSUER, NOW


def _settings(**overrides) -> AuthSettings:
    values = {
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "jwks_url": f"{ISSUER}/protocol/openid-connect/certs",
        "clock_skew_seconds": 0,
    }
    values.update(overrides)
    return AuthSettings(**values)


async def test_valid_bearer_resolves_the_principal(provider, settings, make_token, make_request):
    request = make_request({"authorization": f"Bearer {make_token()}"})

    principal = await current_principal(
        request, settings=settings, provider=provider, clock=lambda: NOW
    )

    assert principal.user_id == "user-1"
    assert principal.tenant_id == "tenant-a"
    assert principal.roles == ("owner",)
    assert principal.auth_time == int(NOW.timestamp()) - 60
    assert principal.acr is None
    assert principal.is_signer is True


async def test_step_up_acr_reaches_the_principal(provider, settings, make_token, make_request):
    request = make_request(
        {"authorization": f"Bearer {make_token(claims={'acr': 'urn:apex:loa:2'})}"}
    )

    principal = await current_principal(
        request, settings=settings, provider=provider, clock=lambda: NOW
    )

    assert principal.acr == "urn:apex:loa:2"
    assert principal.auth_time == int(NOW.timestamp()) - 60


async def test_bearer_wins_over_the_tenant_header(
    provider, settings, make_token, make_request, monkeypatch
):
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")
    request = make_request({"authorization": f"Bearer {make_token()}", "x-tenant-id": "tenant-b"})

    principal = await current_principal(
        request, settings=settings, provider=provider, clock=lambda: NOW
    )

    assert principal.tenant_id == "tenant-a"


async def test_invalid_bearer_is_a_401_problem_without_the_token(
    provider, settings, make_token, make_request
):
    token = make_token(claims={"exp": int(NOW.timestamp()) - 10_000})
    request = make_request({"authorization": f"Bearer {token}"})

    with pytest.raises(Problem) as caught:
        await current_principal(request, settings=settings, provider=provider, clock=lambda: NOW)

    problem = caught.value
    assert problem.status == 401
    assert problem.headers and 'error_description="expired"' in problem.headers["WWW-Authenticate"]
    assert token not in (problem.detail or "")
    assert token not in str(problem)


async def test_other_authorization_schemes_are_refused(provider, settings, make_request):
    request = make_request({"authorization": "Basic dXNlcjpwYXNz"})

    with pytest.raises(Problem) as caught:
        await current_principal(request, settings=settings, provider=provider, clock=lambda: NOW)

    assert caught.value.status == 401


async def test_no_credentials_is_a_401(provider, settings, make_request, monkeypatch):
    monkeypatch.delenv("APEX_ALLOW_TENANT_HEADER", raising=False)

    with pytest.raises(Problem) as caught:
        await current_principal(
            make_request({}), settings=settings, provider=provider, clock=lambda: NOW
        )

    assert caught.value.status == 401


async def test_dev_mode_resolves_the_header_and_dev_roles(
    provider, settings, make_request, monkeypatch
):
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")
    monkeypatch.setenv("APEX_DEV_ROLES", "owner,admin,not-a-role")

    principal = await current_principal(
        make_request({"x-tenant-id": "tenant-dev"}),
        settings=settings,
        provider=provider,
        clock=lambda: NOW,
    )

    assert principal.user_id == "dev"
    assert principal.tenant_id == "tenant-dev"
    assert principal.roles == ("owner", "admin")
    assert principal.auth_time is None
    assert principal.acr is None


async def test_dev_mode_without_the_header_is_a_401(provider, settings, make_request, monkeypatch):
    monkeypatch.setenv("APEX_ALLOW_TENANT_HEADER", "true")

    with pytest.raises(Problem) as caught:
        await current_principal(
            make_request({}), settings=settings, provider=provider, clock=lambda: NOW
        )

    assert caught.value.status == 401


async def test_disabled_auth_never_authenticates_anyone(provider, make_request):
    settings = _settings(auth_disabled=True)
    request = make_request({"authorization": "Bearer whatever"})

    with pytest.raises(Problem) as caught:
        await current_principal(request, settings=settings, provider=provider, clock=lambda: NOW)

    assert caught.value.status == 503


async def test_require_role_allows_and_denies():
    dependency = require_role("admin", "owner")
    allowed = Principal(user_id="u", tenant_id="t", roles=("owner",))
    denied = Principal(user_id="u", tenant_id="t", roles=("viewer",))

    assert await dependency(principal=allowed) is allowed
    with pytest.raises(Problem) as caught:
        await dependency(principal=denied)
    assert caught.value.status == 403


async def test_viewer_never_signs():
    signer = require_signer()
    viewer = Principal(user_id="u", tenant_id="t", roles=("viewer",))
    finance = Principal(user_id="u", tenant_id="t", roles=("finance",))

    with pytest.raises(Problem) as caught:
        await signer(principal=viewer)
    assert caught.value.status == 403
    assert viewer.is_signer is False
    assert finance.is_signer is True
    assert await signer(principal=finance) is finance


def test_require_role_rejects_unknown_and_empty_roles():
    with pytest.raises(ValueError):
        require_role("superuser")
    with pytest.raises(ValueError):
        require_role()
