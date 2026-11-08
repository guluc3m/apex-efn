# Prompt evaluation suite (D4-05)

Golden sets for every versioned prompt in `../prompts/`. Spec §5.6: a prompt cannot change without passing
its suite against **every** configured model endpoint, and an endpoint that fails it does not go to production.

## Layout

- `golden/<prompt>.v<N>.yaml`: cases for one prompt version. Each case has `variables` (render inputs),
  `expect` (deterministic checks, no LLM judge) and `stub_response` (used only in stub mode).
- `checks.py`: the check vocabulary (`equals`, `is_null`, `contains_all`, `list_subset_of`, `min_len`,
  `max_len`, `numbers_in_input`, `mentions_all`).
- `runner.py`: renders the prompt, calls `LLMGateway.chat_structured`, validates with the Pydantic draft
  schema from `apex.agents.schemas`, then runs the checks.

## Run

```bash
cd apps/orchestrator

# Stub mode (CI, no network): each case is pinned to the sha256 of its exact rendered prompt.
uv run python -m evals.runner

# Live mode: every endpoint in the file, same cases, no stub responses.
cp evals/endpoints.example.json /tmp/endpoints.json   # edit base_url, model, capabilities
APEX_EVAL_VLLM_KEY=... uv run python -m evals.runner --endpoints /tmp/endpoints.json
```

Exit code 0 only when every case passes on every endpoint. API keys are read from the environment variable
named by `api_key_env`; they are never stored in the endpoints file.

## Changing a prompt

1. Copy `prompts/<name>.v<N>.jinja` to `v<N+1>`; never edit a released version in place.
2. Copy and adapt `golden/<name>.v<N>.yaml` to `v<N+1>`.
3. Run stub mode, then live mode against each self-hosted engine you support.

Stub mode proves rendering, the structured-output ladder, schema validation and the checks. It does not prove a
real model follows the prompt; only live mode does.

## Open items

- CI wiring (run stub mode on PRs; run live mode nightly against the self-hosted engines) is a
  `platform-request` to DEV-1.
- Golden sets are small on purpose. Extend them with real, anonymised cases once the mock marketplace and
  onboarding exist.
