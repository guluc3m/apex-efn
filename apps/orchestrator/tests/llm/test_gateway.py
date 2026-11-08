"""LLMGateway behaviour tests (spec §5.6, criteria 25, 26, 28, 29).

These run against a local MockTransport fake; the D4-02 stub-based suite lives in test_stub_integration.py.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from apex.common.clock import FixedClock
from apex.llm.accounting import InMemorySink, LLMEvent
from apex.llm.budget import BudgetPolicy, InMemoryBudgetStore, TokenBudget, TokenBudgetExceeded
from apex.llm.config import CapabilityProfile, GuidedDecoding, LLMRole, ResilienceConfig
from apex.llm.gateway import LLMGateway
from apex.llm.redaction import RedactionAction, RedactionGuard, RedactionViolation
from apex.llm.resilience import AllEndpointsUnavailableError, CircuitOpenError
from apex.llm.structured import LadderStep, StructuredOutputError
from apex.llm.transport import LLMHTTPError, LLMTransportError, normalise_base_url

from .fakes import (
    FakeEndpoint,
    chat_body,
    endpoint_cfg,
    provider,
    roles_config,
    secrets,
    tool_body,
)

_UNAVAILABLE = (LLMHTTPError, LLMTransportError, CircuitOpenError, AllEndpointsUnavailableError)
T0 = datetime(2026, 1, 1, tzinfo=UTC)


class Invoice(BaseModel):
    vendor: str
    total_minor: int


MESSAGES = [{"role": "user", "content": "extract the invoice"}]
GOOD = '{"vendor": "ACME", "total_minor": 12050}'
BAD = "not json at all"
SCHEMA_ERR_BODY = (
    '{"error": {"message": "response_format json_schema is not supported by this model"}}'
)


def make_gateway(
    ep: FakeEndpoint,
    *,
    primary_caps: CapabilityProfile | None = None,
    fallback: list[str] | None = None,
    extra_endpoints: dict | None = None,
    budget_limit: int = 100_000,
    policy: BudgetPolicy = BudgetPolicy.STOP,
    sink: InMemorySink | None = None,
    resilience: ResilienceConfig | None = None,
    clock: FixedClock | None = None,
    rng_seed: int = 7,
    sleeps: list[float] | None = None,
) -> tuple[LLMGateway, InMemorySink, TokenBudget]:
    primary = endpoint_cfg(caps=primary_caps, fallback=fallback)
    config = roles_config(primary, extra=extra_endpoints or {})
    if resilience is not None:
        config = config.model_copy(update={"resilience": resilience})
    sink = sink or InMemorySink()
    budget = TokenBudget(InMemoryBudgetStore(), mission_limit=budget_limit, policy=policy)

    async def fake_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    gateway = LLMGateway(
        config_provider=provider(config),
        secrets=secrets(),
        budget=budget,
        sink=sink,
        clock=clock or FixedClock(T0),
        http_client_factory=lambda cfg: ep.client(),
        rng=random.Random(rng_seed),
        sleep=fake_sleep,
    )
    return gateway, sink, budget


async def structured(gw: LLMGateway, schema: type[BaseModel] = Invoice) -> BaseModel:
    return await gw.chat_structured(
        LLMRole.EXTRACTOR,
        MESSAGES,
        schema,
        mission_id="m1",
        tenant_id="t1",
        prompt_version="v1",
    )


# ---------------------------------------------------------------------------
# Transport / config
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "given",
    ["http://h:8000", "http://h:8000/", "http://h:8000/v1", "http://h:8000/v1/"],
)
def test_base_url_tolerates_trailing_v1(given: str) -> None:
    assert normalise_base_url(given) == "http://h:8000"


async def test_transport_uses_only_openai_paths_and_bearer_header() -> None:
    ep = FakeEndpoint(responses=[chat_body("hi")])
    gw, _, _ = make_gateway(ep)
    await gw.chat(LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1")
    assert [c.path for c in ep.calls] == ["/v1/chat/completions"]
    assert ep.calls[0].headers["authorization"] == "Bearer sk-test-SECRET-VALUE-0123456789"


async def test_list_models_uses_get_v1_models() -> None:
    ep = FakeEndpoint(responses=[{"object": "list", "data": [{"id": "model-a"}]}])
    gw, _, _ = make_gateway(ep)
    models = await gw.list_models(tenant_id="t1", role=LLMRole.EXTRACTOR)
    assert models == ["model-a"]
    assert ep.calls[0].path == "/v1/models"


async def test_embed_uses_v1_embeddings() -> None:
    ep = FakeEndpoint(
        responses=[{"data": [{"embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 3}}]
    )
    primary = endpoint_cfg()
    cfg = roles_config(primary).model_copy(
        update={"roles": {**roles_config(primary).roles, LLMRole.EMBEDDER: primary}}
    )
    sink = InMemorySink()
    gw = LLMGateway(
        config_provider=provider(cfg),
        secrets=secrets(),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=10_000),
        sink=sink,
        clock=FixedClock(T0),
        http_client_factory=lambda c: ep.client(),
    )
    vectors = await gw.embed(["hola"], mission_id="m1", tenant_id="t1", prompt_version="v1")
    assert vectors == [[0.1, 0.2]]
    assert ep.calls[0].path == "/v1/embeddings"


# ---------------------------------------------------------------------------
# Capability gating and criterion 25
# ---------------------------------------------------------------------------


async def test_no_response_format_sent_to_endpoint_without_capability() -> None:
    ep = FakeEndpoint(responses=[chat_body(GOOD)])
    gw, _, _ = make_gateway(ep, primary_caps=CapabilityProfile())  # nothing declared
    await structured(gw)
    for call in ep.calls:
        assert "response_format" not in call.body
        assert "tools" not in call.body
        assert "guided_json" not in call.body
        assert "json_schema" not in call.body


async def test_json_schema_step_used_when_declared() -> None:
    ep = FakeEndpoint(responses=[chat_body(GOOD)])
    gw, sink, _ = make_gateway(ep, primary_caps=CapabilityProfile(supports_json_schema=True))
    result = await structured(gw)
    assert result == Invoice(vendor="ACME", total_minor=12050)
    assert ep.calls[0].body["response_format"]["type"] == "json_schema"
    assert sink.events[-1].ladder_step == LadderStep.JSON_SCHEMA.value


async def test_json_object_step_adds_schema_to_prompt() -> None:
    ep = FakeEndpoint(responses=[chat_body(GOOD)])
    gw, sink, _ = make_gateway(ep, primary_caps=CapabilityProfile(supports_json_object=True))
    await structured(gw)
    body = ep.calls[0].body
    assert body["response_format"] == {"type": "json_object"}
    assert any("JSON schema" in m["content"] for m in body["messages"])
    assert sink.events[-1].ladder_step == LadderStep.JSON_OBJECT.value


async def test_tool_call_step_sends_schema_as_function() -> None:
    ep = FakeEndpoint(responses=[tool_body(GOOD)])
    gw, sink, _ = make_gateway(ep, primary_caps=CapabilityProfile(supports_tools=True))
    result = await structured(gw)
    assert result == Invoice(vendor="ACME", total_minor=12050)
    assert ep.calls[0].body["tools"][0]["function"]["name"] == "Invoice"
    assert sink.events[-1].ladder_step == LadderStep.TOOL_CALL.value


async def test_guided_vllm_step_sends_guided_json() -> None:
    ep = FakeEndpoint(responses=[chat_body(GOOD)])
    caps = CapabilityProfile(supports_guided=GuidedDecoding.VLLM_GUIDED_JSON)
    gw, sink, _ = make_gateway(ep, primary_caps=caps)
    await structured(gw)
    assert "guided_json" in ep.calls[0].body
    assert sink.events[-1].ladder_step == LadderStep.GUIDED.value


async def test_guided_llamacpp_step_sends_json_schema_param() -> None:
    ep = FakeEndpoint(responses=[chat_body(GOOD)])
    caps = CapabilityProfile(supports_guided=GuidedDecoding.LLAMACPP_GRAMMAR)
    gw, _, _ = make_gateway(ep, primary_caps=caps)
    await structured(gw)
    assert "json_schema" in ep.calls[0].body


async def test_seed_sent_only_when_supported() -> None:
    ep = FakeEndpoint(responses=[chat_body("x"), chat_body("x")])
    gw, _, _ = make_gateway(ep, primary_caps=CapabilityProfile(supports_seed=False))
    await gw.chat(
        LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1", seed=3
    )
    assert "seed" not in ep.calls[0].body
    ep2 = FakeEndpoint(responses=[chat_body("x")])
    gw2, _, _ = make_gateway(ep2, primary_caps=CapabilityProfile(supports_seed=True))
    await gw2.chat(
        LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1", seed=3
    )
    assert ep2.calls[0].body["seed"] == 3


# ---------------------------------------------------------------------------
# Ladder degradation, repair, loud failure (criterion 26)
# ---------------------------------------------------------------------------


async def test_http_400_unsupported_degrades_to_next_step() -> None:
    bad = (400, SCHEMA_ERR_BODY, {})
    ep = FakeEndpoint(responses=[bad, chat_body(GOOD)])
    caps = CapabilityProfile(supports_json_schema=True, supports_json_object=True)
    gw, sink, _ = make_gateway(ep, primary_caps=caps)
    result = await structured(gw)
    assert result == Invoice(vendor="ACME", total_minor=12050)
    assert ep.calls[0].body["response_format"]["type"] == "json_schema"
    assert ep.calls[1].body["response_format"] == {"type": "json_object"}
    assert sink.events[-1].ladder_step == LadderStep.JSON_OBJECT.value


async def test_bounded_repair_exactly_two_round_trips_then_loud_failure() -> None:
    ep = FakeEndpoint(responses=[chat_body(BAD)])  # always invalid
    gw, sink, _ = make_gateway(ep)  # no native capabilities: straight to plain repair
    with pytest.raises(StructuredOutputError) as info:
        await structured(gw)
    # 1 initial + 2 repairs = 3 round-trips, never more
    assert len(ep.calls) == 3
    plain = [a for a in info.value.attempts if a.step is LadderStep.PLAIN_REPAIR]
    assert len(plain) == 3 and all(a.outcome == "validation_failed" for a in plain)
    assert sink.events[-1].outcome == "error"


async def test_repair_recovers_and_reports_repair_count() -> None:
    ep = FakeEndpoint(responses=[chat_body(BAD), chat_body(BAD), chat_body(GOOD)])
    gw, sink, _ = make_gateway(ep)
    result = await structured(gw)
    assert result == Invoice(vendor="ACME", total_minor=12050)
    assert len(ep.calls) == 3
    assert sink.events[-1].repair_attempts == 2
    assert sink.events[-1].ladder_step == LadderStep.PLAIN_REPAIR.value
    # the repair turn re-prompts with the validation error
    assert any("not valid JSON" in m["content"] for m in ep.calls[1].body["messages"])


async def test_never_returns_default_on_failure() -> None:
    ep = FakeEndpoint(responses=[chat_body('{"vendor": 1}')])  # wrong types, always
    gw, _, _ = make_gateway(ep)
    with pytest.raises(StructuredOutputError):
        await structured(gw)


# ---------------------------------------------------------------------------
# Retries, jitter, breaker (deterministic)
# ---------------------------------------------------------------------------


async def test_retry_with_jitter_is_deterministic_and_honours_retry_after() -> None:
    fail = (503, "busy", {"Retry-After": "2"})
    ep = FakeEndpoint(responses=[fail, fail, chat_body("ok")])
    sleeps: list[float] = []
    cfg = ResilienceConfig(
        max_retries=3, backoff_base_s=0.5, backoff_cap_s=10.0, breaker_failure_threshold=10
    )
    gw, _, _ = make_gateway(ep, resilience=cfg, sleeps=sleeps, rng_seed=11)
    await gw.chat(LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1")
    assert len(ep.calls) == 3
    assert len(sleeps) == 2
    assert all(s >= 2.0 for s in sleeps)  # Retry-After is a lower bound

    # same seed => identical schedule
    ep2 = FakeEndpoint(responses=[fail, fail, chat_body("ok")])
    sleeps2: list[float] = []
    gw2, _, _ = make_gateway(ep2, resilience=cfg, sleeps=sleeps2, rng_seed=11)
    await gw2.chat(
        LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1"
    )
    assert sleeps == sleeps2


async def test_client_error_400_is_not_retried() -> None:
    ep = FakeEndpoint(responses=[(400, "bad request body", {})])
    gw, _, _ = make_gateway(ep)
    with pytest.raises(LLMHTTPError):
        await gw.chat(
            LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1"
        )
    assert len(ep.calls) == 1


async def test_circuit_opens_then_half_open_probe_then_closes() -> None:
    clock = FixedClock(T0)
    fail = (500, "boom", {})
    ep = FakeEndpoint(responses=[fail])
    cfg = ResilienceConfig(max_retries=0, breaker_failure_threshold=2, breaker_open_seconds=30)
    gw, _, _ = make_gateway(ep, resilience=cfg, clock=clock)

    async def call() -> None:
        await gw.chat(
            LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1"
        )

    for _ in range(2):
        with pytest.raises(
            (LLMHTTPError, LLMTransportError, CircuitOpenError, AllEndpointsUnavailableError)
        ):
            await call()
    assert gw.breaker_state(tenant_id="t1", endpoint_id="primary") == "open"

    calls_before = len(ep.calls)
    with pytest.raises(
        (LLMHTTPError, LLMTransportError, CircuitOpenError, AllEndpointsUnavailableError)
    ):
        await call()
    assert len(ep.calls) == calls_before  # short-circuited, no request sent

    clock.advance(timedelta(seconds=31))
    ep.responses = [chat_body("recovered")]
    await call()  # half-open probe succeeds
    assert gw.breaker_state(tenant_id="t1", endpoint_id="primary") == "closed"


async def test_half_open_probe_failure_reopens() -> None:
    clock = FixedClock(T0)
    ep = FakeEndpoint(responses=[(500, "boom", {})])
    cfg = ResilienceConfig(max_retries=0, breaker_failure_threshold=1, breaker_open_seconds=10)
    gw, _, _ = make_gateway(ep, resilience=cfg, clock=clock)
    with pytest.raises(
        (LLMHTTPError, LLMTransportError, CircuitOpenError, AllEndpointsUnavailableError)
    ):
        await gw.chat(
            LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1"
        )
    clock.advance(timedelta(seconds=11))
    with pytest.raises(
        (LLMHTTPError, LLMTransportError, CircuitOpenError, AllEndpointsUnavailableError)
    ):
        await gw.chat(
            LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1"
        )
    assert gw.breaker_state(tenant_id="t1", endpoint_id="primary") == "open"


# ---------------------------------------------------------------------------
# Fallback chain (big -> small -> degrade)
# ---------------------------------------------------------------------------


async def test_fallback_chain_uses_next_endpoint_when_primary_down() -> None:
    primary_ep = FakeEndpoint(responses=[(500, "down", {})])
    small_ep = FakeEndpoint(responses=[chat_body("from small", model="small")])
    small = endpoint_cfg(
        "small", base_url="http://small.local", model="small", api_key_ref="key/small"
    )

    primary = endpoint_cfg(fallback=["small"])
    config = roles_config(primary, extra={"small": small})
    config = config.model_copy(update={"resilience": ResilienceConfig(max_retries=0)})

    def factory(cfg):  # noqa: ANN001
        return primary_ep.client() if cfg.endpoint_id == "primary" else small_ep.client()

    sink = InMemorySink()
    gw = LLMGateway(
        config_provider=provider(config),
        secrets=secrets(),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=100_000),
        sink=sink,
        clock=FixedClock(T0),
        http_client_factory=factory,
    )
    result = await gw.chat(
        LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1"
    )
    assert result.content == "from small"
    assert result.endpoint_id == "small"
    assert sink.events[-1].endpoint_id == "small"


# ---------------------------------------------------------------------------
# Budget (criterion 28)
# ---------------------------------------------------------------------------


async def test_budget_stop_raises_with_user_warning_and_no_call() -> None:
    ep = FakeEndpoint(responses=[chat_body("x")])
    gw, _, _ = make_gateway(ep, budget_limit=50, policy=BudgetPolicy.STOP)
    with pytest.raises(TokenBudgetExceeded) as info:
        await gw.chat(
            LLMRole.EXTRACTOR,
            [{"role": "user", "content": "x" * 300}],
            mission_id="m1",
            tenant_id="t1",
            prompt_version="v1",
        )
    assert "tokens" in info.value.warning
    assert ep.calls == []  # never silently continued


async def test_budget_commit_accumulates_actual_usage() -> None:
    ep = FakeEndpoint(responses=[chat_body("a", prompt=100, completion=50)])
    gw, _, budget = make_gateway(ep, budget_limit=10_000)
    await gw.chat(LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1")
    state = budget.state("m1")
    assert state.committed == 150
    assert state.reserved == 0


async def test_budget_degrade_switches_to_cheaper_fallback() -> None:
    primary_ep = FakeEndpoint(responses=[chat_body("should not run")])
    small_ep = FakeEndpoint(responses=[chat_body("cheap", model="small")])
    small = endpoint_cfg(
        "small",
        base_url="http://small.local",
        model="small",
        api_key_ref="key/small",
        max_output_tokens=16,
    )
    primary = endpoint_cfg(fallback=["small"], max_output_tokens=100_000)
    config = roles_config(primary, extra={"small": small})

    def factory(cfg):  # noqa: ANN001
        return primary_ep.client() if cfg.endpoint_id == "primary" else small_ep.client()

    gw = LLMGateway(
        config_provider=provider(config),
        secrets=secrets(),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=500, policy=BudgetPolicy.DEGRADE),
        sink=InMemorySink(),
        clock=FixedClock(T0),
        http_client_factory=factory,
    )
    result = await gw.chat(
        LLMRole.EXTRACTOR, MESSAGES, mission_id="m1", tenant_id="t1", prompt_version="v1"
    )
    assert result.endpoint_id == "small"
    assert primary_ep.calls == []


async def test_structured_degrade_walks_to_cheaper_fallback_criterion_28() -> None:
    """criterion 28: under ``degrade`` a structured call that does not fit the primary budget is
    served by the cheaper fallback, never silently overrunning the hard limit."""
    primary_ep = FakeEndpoint(responses=[chat_body(GOOD)])
    small_ep = FakeEndpoint(responses=[chat_body(GOOD, model="small")])
    small = endpoint_cfg(
        "small",
        base_url="http://small.local",
        model="small",
        api_key_ref="key/small",
        max_output_tokens=16,
    )
    primary = endpoint_cfg(fallback=["small"], max_output_tokens=100_000)
    config = roles_config(primary, extra={"small": small})

    def factory(cfg):  # noqa: ANN001
        return primary_ep.client() if cfg.endpoint_id == "primary" else small_ep.client()

    sink = InMemorySink()
    gw = LLMGateway(
        config_provider=provider(config),
        secrets=secrets(),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=500, policy=BudgetPolicy.DEGRADE),
        sink=sink,
        clock=FixedClock(T0),
        http_client_factory=factory,
    )
    value = await gw.chat_structured(
        LLMRole.EXTRACTOR, MESSAGES, Invoice, mission_id="m1", tenant_id="t1", prompt_version="v1"
    )
    assert value == Invoice(vendor="ACME", total_minor=12050)
    assert primary_ep.calls == []  # primary never called: budget degraded before any request
    assert len(small_ep.calls) == 1
    assert sink.events[-1].endpoint_id == "small"


async def test_structured_stop_raises_and_never_calls_endpoint_criterion_28() -> None:
    ep = FakeEndpoint(responses=[chat_body(GOOD)])
    gw, _, _ = make_gateway(ep, budget_limit=50, policy=BudgetPolicy.STOP)
    with pytest.raises(TokenBudgetExceeded):
        await gw.chat_structured(
            LLMRole.EXTRACTOR,
            [{"role": "user", "content": "x" * 300}],
            Invoice,
            mission_id="m1",
            tenant_id="t1",
            prompt_version="v1",
        )
    assert ep.calls == []


# ---------------------------------------------------------------------------
# Redaction (criterion 29)
# ---------------------------------------------------------------------------


async def test_redaction_rejects_bearer_and_never_reaches_transport() -> None:
    ep = FakeEndpoint(responses=[chat_body("x")])
    gw, _, _ = make_gateway(ep)
    leaked = [{"role": "user", "content": "auth is Bearer abcdefghijklmnop123456"}]
    with pytest.raises(RedactionViolation) as info:
        await gw.chat(
            LLMRole.EXTRACTOR, leaked, mission_id="m1", tenant_id="t1", prompt_version="v1"
        )
    assert "bearer_token" in info.value.findings
    assert ep.calls == []


async def test_redaction_rejects_caller_sensitive_value() -> None:
    ep = FakeEndpoint(responses=[chat_body("x")])
    gw, _, _ = make_gateway(ep)
    msg = [{"role": "user", "content": "cash balance is 84213.55 EUR"}]
    with pytest.raises(RedactionViolation):
        await gw.chat(
            LLMRole.EXTRACTOR,
            msg,
            mission_id="m1",
            tenant_id="t1",
            prompt_version="v1",
            sensitive_values=["84213.55"],
        )
    assert ep.calls == []


def test_redaction_detects_key_jwt_iban_card_and_pem() -> None:
    guard = RedactionGuard()
    cases = {
        "api_key": "token sk-abcdefghijklmnopqrstuvwx",
        "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk",
        "iban": "pay to ES91 2100 0418 4502 0005 1332",
        "card_number": "card 4111 1111 1111 1111 on file",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----",
    }
    for kind, text in cases.items():
        with pytest.raises(RedactionViolation) as info:
            guard.check_text(text)
        assert kind in info.value.findings, kind


def test_redaction_ignores_non_luhn_digits_and_safe_text() -> None:
    guard = RedactionGuard()
    assert guard.check_text("order 1234567890123 ref") == "order 1234567890123 ref"


def test_mask_mode_replaces_findings() -> None:
    guard = RedactionGuard(action=RedactionAction.MASK)
    out = guard.check_text("key sk-abcdefghijklmnopqrstuvwx end")
    assert "sk-abcdef" not in out and "[REDACTED:api_key]" in out


def test_error_messages_never_contain_the_secret_value() -> None:
    guard = RedactionGuard()
    try:
        guard.check_text("Bearer abcdefghijklmnop123456")
    except RedactionViolation as exc:
        assert "abcdefghijklmnop" not in str(exc)


# ---------------------------------------------------------------------------
# Accounting (LLMEvent fields)
# ---------------------------------------------------------------------------


async def test_accounting_event_fields_are_complete() -> None:
    ep = FakeEndpoint(responses=[chat_body(GOOD, prompt=40, completion=12)])
    primary = endpoint_cfg(cost=(2, 4), gpu=0.5, model="model-a")
    config = roles_config(primary)
    sink = InMemorySink()
    gw = LLMGateway(
        config_provider=provider(config),
        secrets=secrets(),
        budget=TokenBudget(InMemoryBudgetStore(), mission_limit=10_000),
        sink=sink,
        clock=FixedClock(T0),
        http_client_factory=lambda c: ep.client(),
    )
    await gw.chat(
        LLMRole.EXTRACTOR,
        MESSAGES,
        mission_id="mission-9",
        tenant_id="tenant-3",
        prompt_version="extract-v2",
    )
    event = sink.events[-1]
    assert isinstance(event, LLMEvent)
    assert event.mission_id == "mission-9" and event.tenant_id == "tenant-3"
    assert event.role == "extractor" and event.endpoint_id == "primary" and event.model == "model-a"
    assert event.prompt_version == "extract-v2"
    assert (event.tokens_in, event.tokens_out) == (40, 12)
    assert event.latency_ms >= 0
    assert event.outcome == "ok"
    assert event.cost_minor == (40 * 2 + 12 * 4) // 1000
    assert event.gpu_seconds == pytest.approx(52 / 1000 * 0.5)


def test_rolling_aggregator_p50_p95_and_repair_rate() -> None:
    from apex.llm.accounting import RollingAggregator

    agg = RollingAggregator()
    for latency in range(1, 101):
        agg.record(
            LLMEvent(
                "m",
                "t",
                "extractor",
                "ep",
                "m",
                "v",
                1,
                1,
                float(latency),
                "plain_repair",
                1 if latency % 4 == 0 else 0,
                "ok",
            ),
            structured=True,
        )
    p50, p95 = agg.latency_p50_p95("ep")
    assert 50 <= p50 <= 51
    assert 94 <= p95 <= 96
    assert agg.json_repair_rate("extractor") == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Criterion 25: switching only base_url + model
# ---------------------------------------------------------------------------


async def test_switching_only_base_url_and_model_changes_target_not_code() -> None:
    openai_ep = FakeEndpoint(responses=[chat_body(GOOD, model="gpt-x")])
    selfhosted_ep = FakeEndpoint(responses=[chat_body(GOOD, model="qwen-local")])

    async def go(ep: FakeEndpoint, base_url: str, model: str) -> object:
        primary = endpoint_cfg(base_url=base_url, model=model)
        gw = LLMGateway(
            config_provider=provider(roles_config(primary)),
            secrets=secrets(),
            budget=TokenBudget(InMemoryBudgetStore(), mission_limit=10_000),
            sink=InMemorySink(),
            clock=FixedClock(T0),
            http_client_factory=lambda c: ep.client(),
        )
        return await structured(gw)

    a = await go(openai_ep, "https://api.openai.example", "gpt-x")
    b = await go(selfhosted_ep, "http://vllm.internal:8000/v1", "qwen-local")
    assert a == b
    assert openai_ep.calls[0].body["model"] == "gpt-x"
    assert selfhosted_ep.calls[0].body["model"] == "qwen-local"
    assert [c.path for c in selfhosted_ep.calls] == ["/v1/chat/completions"]
    # identical request shape, only model/endpoint differ
    assert set(openai_ep.calls[0].body) == set(selfhosted_ep.calls[0].body)


# ---------------------------------------------------------------------------
# Sanity: no proprietary paths in this module
# ---------------------------------------------------------------------------


def test_no_proprietary_paths_in_llm_package() -> None:
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "apex" / "llm"
    banned = ("/assistants", "/threads", "/batches")
    for path in root.rglob("*.py"):
        text = path.read_text()
        for needle in banned:
            assert needle not in text, f"{needle} found in {path.name}"
