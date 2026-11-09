# ADR-200: OpenAPI contracts as the single source of DTOs, with generated TypeScript, Zod and Pydantic

## Status

Proposed. D2-01 is `TL approval: no`. The closed enums that touch the gate (`DiscardReasonCode`, `GateReason`,
`BlockReasonCode`) are taken as-is from D4-11, which is merged, and ADR-900 answers apply where relevant.

## Context

Spec section 5.1 requires that every DTO shared by the web app, the orchestrator and the tooling comes from a
single contract. The scaffold had hand-written DTOs in `packages/shared-types/src/*.ts` that duplicated the API
and had already drifted from it. Other lanes need compile-time types in TypeScript (web, workers, crypto-client)
and runtime validation models in Python (FastAPI, LangGraph, the LLM structured-output ladder).

## Decision

1. **Source:** `contracts/openapi.yaml` (OpenAPI 3.1.0) is the public contract. `contracts/internal/browser-worker.openapi.yaml`
   is the internal contract for the browser worker (DEV-5 completes it in D5-01).
2. **TypeScript and Zod:** `@hey-api/openapi-ts` pinned to exactly `0.99.0` (devDependency of `@apex/shared-types`), with the
   `@hey-api/typescript` and `zod` plugins. Output goes to `packages/shared-types/src/generated/`. Zod schemas are
   exported through the `@apex/shared-types/contracts/zod` subpath.
3. **Python:** `datamodel-code-generator==0.91.0` (run through `uvx`), `pydantic_v2.BaseModel`, `--enum-field-as-literal one`.
   Output goes to `apps/orchestrator/src/apex/contracts/generated/models.py`. The file is formatted with `ruff==0.17.4`,
   the version pinned in `apps/orchestrator/uv.lock`, and carries `# ruff: noqa: UP035, UP040` because generated code
   uses `TypeAliasType` and `typing` imports.
4. **Generator:** `contracts/scripts/generate.mjs`, exposed as `pnpm contracts:generate`. `--check` (`pnpm contracts:check`)
   regenerates into a temporary directory inside `contracts/` and fails on any byte difference with the committed output.
5. **Legacy shim:** the hand-written DTOs moved to `packages/shared-types/src/legacy/` with `@deprecated` headers. Their
   existing subpaths (`./currency`, `./seller`, ...) now point to `dist/legacy/*` so other lanes keep compiling. The package
   root re-exports generated types and Zod schemas only. The legacy folder is deleted once DEV-3 and DEV-5 migrate off it.
6. **Contract conventions:**
   - Money is `{amount_minor: int64, currency}`. Floats are forbidden for money and FX.
   - `Currency` is the closed enum `EUR | USD | CNY`.
   - Writes require `Idempotency-Key`. Lists use cursor pagination (`items`, `next_cursor`).
   - Errors are RFC 9457 `application/problem+json`.
   - A missing, expired, revoked or exhausted signing session returns `428 {error: "reauth_required", reason}`.
   - A state-changing action is a signed decision. The action endpoint (deal action, gate queue action, config proposal,
     financial snapshot activation) builds the canonical payload on the server and answers `202 DecisionAccepted
     {decision_id, status: pending_signature}`. The client signs with `POST /v1/decisions/{id}/sign`. Nothing changes
     before the signature. The client never sends a `decision_id` to the action endpoint, so it cannot pair an action
     with a decision signed for something else. This matches what D4-03 (ADR-400) and D4-11 already implement.
   - A blocked action answers `409` with a closed `reason` and `blocked: [{action, reason, detail}]` (criterion 16).
   - Signing sessions are opened after a Keycloak step-up (ADR-900 Q11). `auth_at` is the token's `auth_time`. A token
     without the step-up ACR answers `428` with reason `step_up_required`.
   - Unset business configuration values are `null`. They are never invented in the contract. The effective config uses
     the ADR-400 shape: integer `config_version`, `content_hash`, and a `values` map keyed by dotted path with
     `{value, status: set|unset, layer}`.
7. **Inline schemas are hoisted:** every inline enum or object that generates a type name is moved to a named component. Generators
   otherwise produce automatic names (`Status1`) that change when the contract is edited.
8. **Versioning rules:**
   - Additive changes (new optional fields, new endpoints, new schemas) are allowed in place.
   - Renaming or removing a field, changing a type, or narrowing an enum is a breaking change. It needs a new path version
     (`/v2`) or a deprecation window agreed with DEV-2 and the affected lanes.
   - Every contract change goes through a `<TASK-ID>-contract` PR that only touches `/contracts/**` (AGENTS.md 3.5). DEV-2 approves.
   - Generated files are never edited by hand. `pnpm contracts:check` must pass in CI (D1-04).

## Consequences

- Both languages compile against the same types. Drift between the contract and the code is caught by `contracts:check`.
- Generated code is committed, so reviewers see contract changes as code diffs, and consumers do not need the generator to build.
- `openapi-ts` 0.99 deprecates the `format` and `lint` options in favour of `postProcess: []`. We use `postProcess: []` and
  format with the repo's Prettier from the generator, so the output matches `.prettierrc`.
- **Prettier ignores files outside the repository.** A temporary directory under `/tmp` is therefore never formatted, and
  the drift check would fail for a formatting reason only. The check uses a directory inside `contracts/`.
- **Precision risk on the JavaScript side:** `int64` money above `2^53 - 1` (about 9.0 × 10^15 minor units) cannot be represented
  exactly as a TypeScript `number`. The generated TS types use `number` for `int64`. The Python side is exact. Consumers in TS must
  treat amounts as opaque or use `bigint` until ADR-301 (D3-02) decides the TS money representation. Money must not be computed
  in TypeScript beyond display formatting.
- Pinning `openapi-ts` to an exact version means upgrades are deliberate and reviewed. The pinned version and the Python tool
  versions are part of the generator's contract with CI.
- Generated Python lives under `apex/contracts/generated/` (the `apex/contracts/` package comes from D4-01).
- `apps/orchestrator/tests/contracts/test_routes_match_contract.py` fails when FastAPI serves an operation that the
  contract does not declare, or the other way round. A new route therefore needs a contract PR first.
- Routes DEV-4 added before the contract existed are now declared: `PATCH /v1/onboarding/sessions/{id}`,
  `GET /v1/config/effective`, `POST /v1/config/proposals` and `POST /v1/gate/queue/{id}/actions`.
- ADR-900 is reflected in the enums: `OnInsufficientReference` is only `gate` (Q12), `CounterpartType` uses the
  `neg.allowed_counterparts` values (Q15), and `AuthMethod` is `keycloak_step_up` (Q11).
- **Known gaps, follow-up D2-01b with DEV-4.** The route set matches, but some DTOs do not yet:
  - DEV-4's interim response models are loose (`dict`, `str`) where the contract has typed schemas, such as offers,
    seller confidence, deals and recommendations. They should switch to `apex.contracts.generated.models` once the DEV-3
    engines and the DEV-2 data layer exist.
  - `POST /v1/onboarding/{id}/financial-csv/activate` takes JSON `{import_id}` in the contract and a form field
    `snapshot_id` in the current route.
  - Some request bodies carry `roles`. Roles must come from the token (`current_principal()`, D1-05), never from the body.
  - `config_version` is an integer in the config endpoints (ADR-400) and a string in other DTOs (sanity checks,
    confidences, decisions). One type should be used everywhere.
  Until these are aligned, the contract is authoritative for clients, and the parity test only checks paths and methods.

## Related

- AGENTS.md section 2 (ownership of `/contracts/**` and `/packages/shared-types/**`), section 3.5 (cross-lane contract changes), section 5 (D2-01)
- PROMPT-IMPLEMENTACION.md section 5.1 (contracts), section 8 (API)
- ADR-001 (monorepo structure), ADR-002 (OpenAI-compatible LLM gateway)
- ADR-301 (money representation, D3-02), to be written by DEV-3
- ADR-201 (migration ownership, D2-02), to be written by DEV-2 for TL approval
