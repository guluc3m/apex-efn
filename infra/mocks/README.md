# infra/mocks

The Mockoon OpenAI stub that used to live here has been **replaced** by the scenario-driven
stub in [`apps/llm-stub`](../../apps/llm-stub/README.md) (D4-02). Mockoon could not simulate
structured-output degradation, tool calls, malformed JSON or retry scenarios.

- Use `apps/llm-stub` for local dev, tests and compose (port 8001).
- Scenario fixtures and the matching rules are documented in `apps/llm-stub/README.md`.
- Compose wiring is proposed in `apps/llm-stub/COMPOSE_SNIPPET.md` (owned by DEV-1).
