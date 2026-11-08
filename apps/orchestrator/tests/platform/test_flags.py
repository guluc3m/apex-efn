import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from apex.platform.flags import StaticFlags, UnleashFlags, validate_flag_name

TOKEN = "default:development.apex-dev-unleash-client-SECRET-XYZ"
BASE_URL = "http://unleash.test:4242/api/"
NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)

# Shaped like GET /api/client/features on unleash-server 8.x (client API, "version": 2).
FEATURES_PAYLOAD: dict[str, Any] = {
    "version": 2,
    "features": [
        {
            "name": "platform.mock-a.enabled",
            "type": "release",
            "project": "default",
            "enabled": True,
            "stale": False,
            "strategies": [
                {"name": "default", "constraints": [], "parameters": {}, "segments": []}
            ],
            "variants": [],
            "description": "Mock marketplace A",
            "impressionData": False,
        },
        {
            "name": "platform.mock-b.enabled",
            "type": "release",
            "project": "default",
            "enabled": False,
            "stale": False,
            "strategies": [
                {"name": "default", "constraints": [], "parameters": {}, "segments": []}
            ],
            "variants": [],
            "impressionData": False,
        },
        {
            "name": "negotiation.autonomous_send",
            "type": "kill-switch",
            "project": "default",
            "enabled": True,
            "stale": False,
            "strategies": [
                {
                    "name": "flexibleRollout",
                    "constraints": [],
                    "parameters": {"rollout": "0", "stickiness": "default", "groupId": "x"},
                    "segments": [],
                }
            ],
            "variants": [],
            "impressionData": False,
        },
        {
            "name": "sanity.bands.v1",
            "type": "release",
            "project": "default",
            "enabled": True,
            "stale": False,
            "strategies": [
                {
                    "name": "flexibleRollout",
                    "constraints": [],
                    "parameters": {"rollout": "50", "stickiness": "default", "groupId": "y"},
                    "segments": [],
                }
            ],
            "variants": [],
            "impressionData": False,
        },
        {
            "name": "trust.model.v2",
            "type": "release",
            "project": "default",
            "enabled": True,
            "stale": False,
            "strategies": [
                {
                    "name": "default",
                    "constraints": [
                        {
                            "contextName": "appName",
                            "operator": "IN",
                            "values": ["apex-orchestrator"],
                            "caseInsensitive": False,
                            "inverted": False,
                        }
                    ],
                    "parameters": {},
                    "segments": [],
                }
            ],
            "variants": [],
            "impressionData": False,
        },
        {
            "name": "negotiation.strategy.anchor-first",
            "type": "release",
            "project": "default",
            "enabled": True,
            "stale": False,
            "strategies": [
                {
                    "name": "userWithId",
                    "constraints": [],
                    "parameters": {"userIds": "u1"},
                    "segments": [],
                }
            ],
            "variants": [],
            "impressionData": False,
        },
        {
            "name": "negotiation.strategy.volume-tiers",
            "type": "release",
            "project": "default",
            "enabled": True,
            "stale": False,
            "strategies": [],
            "variants": [],
            "impressionData": False,
        },
    ],
    "query": {"environment": "development", "namePrefix": "", "tag": []},
}


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    clock: Callable[[], datetime] = lambda: NOW,
) -> UnleashFlags:
    return UnleashFlags(
        base_url=BASE_URL,
        client_token=TOKEN,
        transport=httpx.MockTransport(handler),
        clock=clock,
    )


def _serving(payload: dict[str, Any]) -> UnleashFlags:
    client = _client(lambda request: httpx.Response(200, json=payload))
    assert client.refresh() is True
    return client


def test_unknown_flag_is_off() -> None:
    assert _serving(FEATURES_PAYLOAD).is_enabled("platform.unknown-one.enabled") is False


def test_flag_never_fetched_is_off() -> None:
    client = _client(lambda request: httpx.Response(200, json=FEATURES_PAYLOAD))
    assert client.is_platform_enabled("mock-a") is False


def test_unreachable_server_is_off_and_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _client(refuse)
    with caplog.at_level(logging.WARNING, logger="apex.platform.flags"):
        assert client.refresh() is False
    assert client.is_enabled("platform.mock-a.enabled") is False
    assert "ConnectError" in caplog.text


def test_disabled_toggle_is_off() -> None:
    assert _serving(FEATURES_PAYLOAD).is_platform_enabled("mock-b") is False


def test_enabled_default_strategy_is_on() -> None:
    client = _serving(FEATURES_PAYLOAD)
    assert client.is_platform_enabled("mock-a") is True


def test_flexible_rollout_100_is_on_and_0_is_off() -> None:
    payload = json.loads(json.dumps(FEATURES_PAYLOAD))
    rollout = payload["features"][2]["strategies"][0]
    rollout["parameters"]["rollout"] = "100"
    client = _serving(payload)
    assert client.is_enabled("negotiation.autonomous_send") is True
    rollout["parameters"]["rollout"] = "0"
    assert _serving(payload).is_enabled("negotiation.autonomous_send") is False


def test_flexible_rollout_partial_is_off_and_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    client = _serving(FEATURES_PAYLOAD)
    with caplog.at_level(logging.WARNING, logger="apex.platform.flags"):
        assert client.is_enabled("sanity.bands.v1") is False
        assert client.is_enabled("sanity.bands.v1") is False
    assert caplog.text.count("partial rollout 50%") == 1


def test_unknown_strategy_is_off() -> None:
    assert _serving(FEATURES_PAYLOAD).is_enabled("negotiation.strategy.anchor-first") is False


def test_strategy_with_constraints_is_off() -> None:
    assert _serving(FEATURES_PAYLOAD).is_enabled("trust.model.v2") is False


def test_enabled_with_no_strategies_is_on() -> None:
    assert _serving(FEATURES_PAYLOAD).is_enabled("negotiation.strategy.volume-tiers") is True


@pytest.mark.parametrize(
    "name",
    [
        "Platform.mock-a.enabled",
        "platform.mock-a",
        "platform.mock a.enabled",
        "platform..enabled",
        "platform.mock-a.enabled.extra",
        "sanity.bands.v1.0",
        "negotiation.autonomous-send",
        "something.else",
        "",
    ],
)
def test_malformed_name_raises(name: str) -> None:
    client = _serving(FEATURES_PAYLOAD)
    with pytest.raises(ValueError, match="malformed feature flag name"):
        client.is_enabled(name)
    with pytest.raises(ValueError):
        StaticFlags().is_enabled(name)


def test_valid_names_pass_validation() -> None:
    for name in (
        "platform.mock-a.enabled",
        "negotiation.strategy.anchor_first",
        "negotiation.autonomous_send",
        "sanity.bands.v1",
        "trust.model.v2",
    ):
        assert validate_flag_name(name) == name


def test_last_snapshot_is_kept_after_failed_refresh(caplog: pytest.LogCaptureFixture) -> None:
    responses = iter([httpx.Response(200, json=FEATURES_PAYLOAD), httpx.Response(503)])
    client = _client(lambda request: next(responses))
    assert client.refresh() is True
    with caplog.at_level(logging.WARNING, logger="apex.platform.flags"):
        assert client.refresh() is False
    assert client.is_platform_enabled("mock-a") is True
    assert "keeping last snapshot of 7 flags" in caplog.text


def test_malformed_payload_keeps_snapshot() -> None:
    responses = iter(
        [httpx.Response(200, json=FEATURES_PAYLOAD), httpx.Response(200, json={"x": 1})]
    )
    client = _client(lambda request: next(responses))
    client.refresh()
    assert client.refresh() is False
    assert client.is_platform_enabled("mock-a") is True


def test_request_carries_token_headers_and_trailing_slash_is_normalised() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=FEATURES_PAYLOAD)

    client = UnleashFlags(
        base_url="http://unleash.test/api///",
        client_token=TOKEN,
        app_name="apex-orchestrator",
        instance_id="pod-1",
        transport=httpx.MockTransport(handler),
    )
    client.refresh()
    request = seen[0]
    assert str(request.url) == "http://unleash.test/api/client/features"
    assert request.headers["Authorization"] == TOKEN
    assert request.headers["UNLEASH-APPNAME"] == "apex-orchestrator"
    assert request.headers["UNLEASH-INSTANCEID"] == "pod-1"


def test_last_refreshed_at_uses_injected_clock() -> None:
    client = _client(lambda request: httpx.Response(200, json=FEATURES_PAYLOAD))
    assert client.last_refreshed_at is None
    client.refresh()
    assert client.last_refreshed_at == NOW


def test_token_never_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    def fail_with_body(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"bad token echoed {request.headers['Authorization']}")

    client = _client(fail_with_body)
    with caplog.at_level(logging.DEBUG):
        client.refresh()
        client.is_platform_enabled("mock-a")
        client.is_enabled("negotiation.strategy.anchor-first")
    assert TOKEN not in caplog.text
    assert "SECRET-XYZ" not in caplog.text
    for record in caplog.records:
        assert TOKEN not in record.getMessage()


def test_from_env_requires_url_and_token() -> None:
    with pytest.raises(ValueError):
        UnleashFlags.from_env({"UNLEASH_URL": "http://x/api"})
    with pytest.raises(ValueError):
        UnleashFlags.from_env({"UNLEASH_API_TOKEN": TOKEN})


def test_from_env_builds_client() -> None:
    client = UnleashFlags.from_env(
        {"UNLEASH_URL": "http://unleash.test:4242/api", "UNLEASH_API_TOKEN": TOKEN},
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=FEATURES_PAYLOAD)),
    )
    assert client.refresh() is True
    assert client.is_platform_enabled("mock-a") is True


async def test_poll_refreshes_until_stopped() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        loop.call_soon_threadsafe(stop.set)
        return httpx.Response(200, json=FEATURES_PAYLOAD)

    client = _client(handler)
    await client.poll(interval_seconds=3600, stop=stop)
    assert calls == 1
    assert client.is_platform_enabled("mock-a") is True


def test_static_flags_implement_the_provider_contract() -> None:
    flags = StaticFlags({"platform.mock-a.enabled": True, "negotiation.autonomous_send": False})
    assert flags.is_platform_enabled("mock-a") is True
    assert flags.is_platform_enabled("mock-b") is False
    assert flags.is_enabled("negotiation.autonomous_send") is False
    assert flags.is_enabled("sanity.bands.v9") is False
