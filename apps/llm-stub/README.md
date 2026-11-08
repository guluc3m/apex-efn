# llm-stub

OpenAI-compatible HTTP stub for APEX-EFN tests (D4-02). No network, no real models. Scenario fixtures
drive responses, so the orchestrator's `LLMGateway` can be tested against capability gaps,
malformed JSON, tool calls, latency and 5xx/429 without touching a model.

Scope of this part (02a): `POST /v1/chat/completions` (non-streaming), `POST /v1/embeddings`,
`GET /v1/models`, `GET /health`. Streaming, `/_stub/*` admin and the `llm_stub.testing` plugin
land in 02b.

## Scenario selection

Priority, highest first:

1. Header `X-Stub-Scenario: <name>`.
2. A scenario whose criteria match (AND-ed; most specific wins: `models`=1, `role`=2, `prompt_sha256`=4):
   - `models: [...]` — request `model` is listed.
   - `role: planner|negotiator|extractor|narrator` — the system message contains `role: <name>`.
   - `prompt_sha256: <hex>` — sha256 of the canonical JSON of `[{role, content}, ...]`.
3. The scenario named `default` (required). Scenarios without criteria are never picked by rule 2.

## Scenario format (YAML or JSON)

```yaml
scenarios:
  - name: no-json-schema          # required, unique across files
    description: "..."
    models: [stub-model]          # optional match
    role: negotiator              # optional match
    capabilities:                 # per model id; "*" = any unlisted model
      "*":
        supports_json_schema: false
        supports_json_object: true
        supports_tools: false
        supports_streaming: true
        supports_seed: true
        supports_guided: false    # vLLM guided_json / llama.cpp grammar
    behaviour:
      fail_times: 0               # first N calls return fail_with
      fail_with: {status: 503, message: "...", type: server_error, retry_after: null}
      timeout_sleep_ms: null      # sleep before answering
      usage: {prompt_tokens: 5}   # override usage for all responses
      echo_seed: true             # system_fingerprint "stub-seed-<n>" when seed sent
    response:                     # OR sequence: [ ... ] (nth call -> nth element; last repeats)
      kind: json                  # json | text | tool_call | error
      content: {"result": "valid"}
      delay_ms: 0
      usage: {prompt_tokens: 5, completion_tokens: 7}
      finish_reason: stop
    embedding_dim: 64
```

- `json` / `text`: `content` is the assistant message; objects are serialized compactly with
  sorted keys. Malformed output is written as `kind: text` with the broken string.
- `tool_call`: `tool_call: {name, arguments, id}`; `arguments` is serialized to a JSON string.
  `finish_reason: tool_calls`, `content: null`.
- `error`: `error: {status, message, type, retry_after}` as an OpenAI-style error body;
  `retry_after` sets `Retry-After`.

Load-time validation rejects unknown keys and missing `default`.

## Capability enforcement

Requests using a feature the matched model does not declare get **400** (`invalid_request_error`):

| Request field | Capability |
|---|---|
| `response_format.type = json_schema` | `supports_json_schema` |
| `response_format.type = json_object` | `supports_json_object` |
| `tools` | `supports_tools` |
| `stream: true` | `supports_streaming` |
| `seed` | `supports_seed` |
| `guided_json` / `grammar` | `supports_guided` |

Capabilities are never inferred.

## Token usage

Deterministic approximation, not a tokenizer: prompt = Σ(`4 + ceil(chars/4)`) per message;
completion = `ceil(chars/4)` (min 1 if non-empty); total = sum. Scenario `behaviour.usage` or
per-response `usage` overrides the counters.

## Embeddings

Unit-length vectors derived from sha256 of each input; same input gives the same vector.
Dimension from the scenario's `embedding_dim` (default 64).

## Latency and failures

- `delay_ms` and `behaviour.timeout_sleep_ms` sleep before answering.
- `fail_times` + `fail_with` fail the first N calls of a scenario, then succeed. Counters are
  per scenario and per app instance (a fresh app starts fresh).
- The in-process ASGI transport does not enforce httpx timeouts; emulate caller timeouts with
  `asyncio.wait_for`.

## Bundled scenarios

| Name | Behaviour |
|---|---|
| `default` | Full capability, valid JSON. Fallback. |
| `full-capability` | Declares every capability; valid JSON. |
| `no-json-schema` | No `json_schema`; json_object, tools, streaming, seed. |
| `json-object-only` | Only `json_object`. |
| `tools-only` | Tool calls only. |
| `plain-text-only` | Prose only (forces the repair path). |
| `malformed-then-valid` | Truncated JSON, then valid. |
| `always-malformed` | Trailing prose, fenced JSON, wrong shape. |
| `flaky-5xx` | First 2 calls 503, then success. |
| `rate-limited` | First call 429 + `Retry-After: 2`, then success. |
| `slow` | 1500 ms latency. |
| `timeout` | Sleeps 60 s (for tests with a short caller budget). |
| `huge-usage` | Usage 900 000 / 100 000 for budget tests. |
| `role-planner`, `role-negotiator`, `role-extractor`, `role-narrator` | Matched by the `role:` marker. |

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest
```
