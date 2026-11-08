# llm-stub

A standalone, **OpenAI-compatible** HTTP stub used by APEX-EFN tests and local development. It
replaces real model calls: no network, no paid models, deterministic output driven by
**scenario fixtures**. It speaks only the OpenAI wire format (spec §5.6), so the same
`LLMGateway` code that talks to vLLM/llama.cpp/Ollama talks to it.

Owner: DEV-4 (lane: Orchestrator, Agents & LLM). Task: D4-02.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/chat/completions` | Non-streaming JSON, or `stream: true` as SSE (`data: {chunk}` lines, terminated by `data: [DONE]`). |
| POST | `/v1/embeddings` | Deterministic unit vectors from sha256 of each input. Dimension from scenario `embedding_dim` (default 64). |
| GET | `/v1/models` | Lists model ids declared by scenarios (`models:` lists and capability keys). |
| GET | `/health` | `{"status": "ok"}`. |

Admin endpoints live **outside** `/v1`, under `/_stub/`:

| Method | Path | Purpose |
|---|---|---|
| POST | `/_stub/reset` | Reset per-scenario call counters (sequences, fail-N-times) and clear the call log. |
| GET | `/_stub/scenarios` | Loaded scenarios with declared capabilities and call counts. |
| GET | `/_stub/calls` | Log of received requests (`path`, `scenario`, `status`, `headers`, `body`). Authorization and cookie headers are never recorded. |
| DELETE | `/_stub/calls` | Clear the call log only. |

Unknown `X-Stub-Scenario` values return 400 with `code: scenario_not_found`.

## Running

```bash
cd apps/llm-stub
uv sync
LLM_STUB_SCENARIOS_DIR=$PWD/scenarios uv run python -m llm_stub   # port 8001
```

Environment: `LLM_STUB_SCENARIOS_DIR` (default: bundled `scenarios/`), `LLM_STUB_HOST`
(default `0.0.0.0`), `LLM_STUB_PORT` (default `8001`).

## Scenario selection

Priority, highest first:

1. Header `X-Stub-Scenario: <name>` — explicit, always wins.
2. A scenario whose criteria match the request. Criteria are AND-ed; the most specific match wins
   (score: `models` = 1, `role` = 2, `prompt_sha256` = 4):
   - `models: [model-id, ...]` — the request `model` is in the list.
   - `role: planner|negotiator|extractor|narrator` — the **system** message contains
     `role: <name>` (case-insensitive).
   - `prompt_sha256: <hex>` — sha256 of the canonical JSON of the messages
     (`[{role, content}, ...]`, sorted keys, compact separators). Useful to pin one exact prompt.
3. The scenario named `default`. A scenario with no match criteria is never selected by rule 2.

## Scenario format

Scenarios are YAML or JSON files in the scenarios directory. A file may contain one scenario, a
list, or `{scenarios: [...]}`. Names must be unique across files, and a `default` scenario is
required. Unknown keys are rejected at load time (fail fast).

```yaml
scenarios:
  - name: no-json-schema            # required, unique
    description: "free text"        # optional
    models: [stub-model]            # optional match criteria
    role: negotiator                # optional match criteria
    prompt_sha256: "abc…"           # optional match criteria
    capabilities:                   # per model id; "*" = any model not listed
      "*":
        supports_json_schema: false
        supports_json_object: true
        supports_tools: false
        supports_streaming: true
        supports_seed: true
        supports_guided: false      # vLLM guided_json / llama.cpp grammar
    behaviour:                      # optional
      fail_times: 0                 # first N calls return fail_with
      fail_with: {status: 503, message: "...", type: server_error, retry_after: null}
      timeout_sleep_ms: null        # sleep this long before answering (see caveat below)
      usage: {prompt_tokens: 5}     # override usage for all responses
      echo_seed: true               # echo seed as system_fingerprint "stub-seed-<n>"
    response:                       # one response, OR use sequence
      kind: json                    # json | text | tool_call | error
      content: {"result": "valid"}  # json (object/array/scalar) or text
      delay_ms: 0                   # latency for this response
      usage: {prompt_tokens: 5, completion_tokens: 7}   # per-response override
      finish_reason: stop           # optional override
    # sequence:                     # nth call returns nth element; last element repeats
    #   - {kind: text, content: '{"a": 1'}
    #   - {kind: json, content: {"a": 1}}
    embedding_dim: 64
```

Response kinds:

- `json` / `text`: `content` is rendered as the assistant message. A JSON object/array is
  serialized compactly with sorted keys. Malformed JSON is expressed with `kind: text` and the
  broken string (truncated, trailing prose, or ```` ```json ```` fences).
- `tool_call`: `tool_call: {name, arguments, id}`. `arguments` may be an object (serialized) or a
  raw string (passed through). Returns `finish_reason: tool_calls` and `content: null`.
- `error`: `error: {status, message, type, retry_after}` returned as an HTTP error with an
  OpenAI-style body. `retry_after` sets the `Retry-After` header.

### Capability enforcement

A request that uses a feature the matched model does not declare gets **HTTP 400** with an
OpenAI-style `invalid_request_error` body and a message naming the feature. Checked features:

| Request field | Required capability |
|---|---|
| `response_format.type = json_schema` | `supports_json_schema` |
| `response_format.type = json_object` | `supports_json_object` |
| `tools` | `supports_tools` |
| `stream: true` | `supports_streaming` |
| `seed` | `supports_seed` |
| `guided_json` / `grammar` | `supports_guided` |

Capabilities are never inferred: an undeclared capability is unsupported.

### Schema validation

When a `json_schema` (or `guided_json`) is supplied, the stub validates the *scripted* content
against it only for the gateway's benefit by returning whatever the scenario says. Deliberately
non-conforming content (wrong shape, malformed JSON) is produced by scenarios such as
`always-malformed`, so gateway tests can assert the validation and repair logic.

### Latency, failures and timeouts

- `response.delay_ms` and `behaviour.timeout_sleep_ms` sleep before answering.
- `behaviour.fail_times` + `fail_with` fail the first N calls of the scenario, then succeed.
  Counters are per scenario and reset with `POST /_stub/reset`.
- **Caveat:** the in-process ASGI transport used by `llm_stub.testing` does not enforce httpx
  timeouts. Emulate caller timeouts with `asyncio.wait_for`. Real-socket timeouts work when the
  stub is run with uvicorn (compose).

## Token usage

Deterministic approximation, not a real tokenizer:

- `prompt_tokens` = Σ over messages of `4 + ceil(chars / 4)` (4 is per-message overhead).
- `completion_tokens` = `ceil(chars / 4)` of the produced content (minimum 1 when non-empty).
- `total_tokens` = prompt + completion.
- Overrides: `behaviour.usage` (scenario) or `response.usage` (per response) replace the
  counters; `total_tokens` is recomputed from the two values.

## Bundled scenarios

| Name | Behaviour |
|---|---|
| `default` | Full capability; valid JSON object. Fallback. |
| `full-capability` | Declares every capability; valid JSON. |
| `no-json-schema` | No `json_schema`; `json_object`, tools, streaming, seed supported. |
| `json-object-only` | Only `json_object`; everything else → 400. |
| `tools-only` | Tool calls only (`tool_calls`, `finish_reason: tool_calls`). |
| `plain-text-only` | No structured output; prose (forces the repair path). |
| `malformed-then-valid` | Call 1: truncated JSON; then valid JSON. |
| `always-malformed` | Trailing prose, fenced JSON, then wrong-shape JSON, repeating. |
| `flaky-5xx` | First 2 calls → 503, then success. |
| `rate-limited` | First call → 429 with `Retry-After: 2`, then success. |
| `slow` | 1500 ms latency per answer. |
| `timeout` | Sleeps 60 s (only useful with a real socket and a shorter client timeout). |
| `huge-usage` | Usage 900 000 prompt / 100 000 completion, for budget-exhaustion tests. |
| `role-planner` / `role-negotiator` / `role-extractor` / `role-narrator` | Matched by the `role:` marker in the system message. |

## In-process testing (`llm_stub.testing`)

```python
# conftest.py of the consuming package
pytest_plugins = ["llm_stub.testing"]


# test_gateway.py
async def test_no_response_format_when_unsupported(llm_stub) -> None:
    r = await llm_stub.post(
        "/v1/chat/completions",
        json={
            "model": "m",
            "messages": [{"role": "user", "content": "hi"}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "x", "schema": {}}},
        },
        headers={"X-Stub-Scenario": "no-json-schema"},
    )
    assert r.status_code == 400
    assert (await llm_stub.calls())[-1]["status"] == 400
```

- Fixture `llm_stub` (`StubClient`, function scope, fresh counters): `post`, `get`, `delete`
  (httpx responses), `base_url`, `http` (underlying `httpx.AsyncClient`), `await reset()`,
  `await calls()`, `await clear_calls()`.
- Fixture `llm_stub_scenarios_dir`: override to use your own scenario directory.
- Programmatic: `llm_stub.testing.mount_stub(scenarios_dir) -> httpx.AsyncClient` (close with
  `aclose()`).
- `llm_stub.create_app(scenarios_dir)` returns the FastAPI app for other ASGI setups.

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest
```

No real model calls, no network access required.
