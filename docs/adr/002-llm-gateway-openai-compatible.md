# ADR-002: LLM Gateway with OpenAI-Compatible API

## Status

Accepted

## Context

TRATO needs to access LLMs for:
- Natural language understanding (sourcing requests)
- Planning (which platforms to query)
- Negotiation (conducting chat conversations)
- Explanation (generating human-readable summaries)

We want to:
1. Support multiple LLM providers (OpenAI, Anthropic, self-hosted)
2. Enable self-hosted deployment for cost control and data privacy
3. Avoid vendor lock-in to any single provider
4. Keep the codebase simple with a single integration pattern

## Decision

All LLM access goes through a single `LLMGateway` class that uses **only the OpenAI-compatible HTTP API**:

- `POST /v1/chat/completions`
- `POST /v1/embeddings`
- `GET /v1/models`

**Prohibited:**
- Proprietary endpoints (Assistants API, Batch API)
- SDKs that don't accept `base_url` override
- Provider-specific response formats

**Configuration:**
- Different `base_url` per role (planner, negotiator, extractor, embedder)
- Capability profiles per endpoint (supports_json_schema, context_window, etc.)
- Fallback chain: large model → small model → graceful degradation

**Structured output escalation ladder:**
1. `response_format: json_schema` (if supported)
2. `response_format: json_object` + schema in prompt
3. Function calling with schema
4. Guided decoding (vLLM, llama.cpp)
5. Parse with repair (max 2 attempts, loud failure)

## Consequences

### Easier
- Switch between OpenAI and self-hosted (vLLM, TGI, Ollama) with config change
- Consistent interface across all agents
- CI can run with a local stub server
- Cost control via token budgets

### Harder
- Cannot use advanced features like OpenAI Assistants
- Must implement our own prompt caching strategy
- Some features (structured output) may not work on all endpoints

## Related

- [Section 5.6 of PROMPT-IMPLEMENTACION.md](../../PROMPT-IMPLEMENTACION.md)
- [trato/llm/gateway.py](../../apps/orchestrator/src/trato/llm/gateway.py)
