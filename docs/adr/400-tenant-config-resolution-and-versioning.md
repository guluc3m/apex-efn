# ADR-400: Tenant configuration resolution, versioning and change control

## Status

Proposed (TL gate: `needs-tech-lead`, issue #48 / D4-03). Draft-quality implementation is built behind
interfaces because `apex.db` (D2-05) and `apex.signing` (DEV-2) are not merged yet.

## Context

PROMPT-IMPLEMENTACION.md §7 requires that no business threshold is hardcoded. Every value is read from
versioned configuration, changing one is a signed decision that creates a new version, and evaluations
store `config_version` so they are reproducible. Several keys are explicitly "sin definir" (not defined)
and must be supplied by the tenant; the system must never invent them. Criterion 5 requires that changing
`sanity.z_gate` changes classification without a deploy and produces a signed decision.

AGENTS.md §6 forbids business defaults in code and requires that engines receive config and `now` as
parameters.

## Decision

### 1. Layers and resolution order

For a given `(tenant_id, category)` the effective configuration is resolved from three layers, lowest
precedence first:

1. **global**: `config/defaults/tenant-config.v1.json` (shipped with the release; the only layer that
   may define non-tenant values such as `money.supported_currencies` and `fx.pivot`).
2. **tenant**: the tenant's latest active version of its configuration.
3. **category override**: the tenant's per-category overrides (keys whose scope includes `category`,
   e.g. `sanity.z_gate` per category), applied on top of the tenant layer for that category only.

Resolution is performed per key. For each key the resolver returns the value, the layer it came from
(`global | tenant | category`) and the version of that layer (`resolved_at` provenance). A key defined in
no layer is returned as **explicitly unset** (see §3), never omitted and never defaulted.

### 2. Deep-merge semantics

- Objects are merged key by key, recursively. A nested key in a higher layer overrides only that key.
- Scalars and arrays are replaced wholesale (arrays are never merged element-wise).
- An empty object `{}` in a patch merges nothing: it does not erase the existing subtree.
- An explicit `null` in a higher layer means **unset**: it overrides the lower layer's value and makes the
  key unset again. This is the only way a tenant can "unset" a key.
- Deep-merge is associative and idempotent over layers (`merge(a, merge(b, c)) == merge(merge(a, b), c)`,
  `merge(a, a) == a`) **for shape-consistent layers**: every path is either always a leaf (a scalar, or
  `null` for unset) or always an object. All layers are validated against the same config schema, which
  guarantees that. Across shapes, a `null` over an object replaces the whole subtree and the merge is not
  associative (`a={x:{y:null}}, b={x:null}, c={x:{z:null}}` merges to different results in the two
  groupings). Property tests generate shape-consistent layers and a separate test pins the counterexample.
  Consequence: the service must reject a layer whose shape differs from the schema; it must not rely on
  merge order to tolerate it. (Tech lead: confirm that keys that are objects in the schema, such as
  `llm.roles.*`, may not be set to `null` as a whole, only their leaves.)

### 3. Unset keys ("sin definir") — loud failure, never a default

- Keys marked "sin definir" in §7 (`sanity.floor_per_unit`, `sanity.ceiling_per_unit`, `neg.target_discount`,
  `neg.max_discount`, `approval.threshold`, `approval.dual_control_above`,
  `signing.high_value_reauth_above`, `llm.roles.*`) and `seller.weights.*` ("ver ADR", pending ADR-304)
  ship as `null` in v1 with `unset` status.
- The effective view returns them as `Unset(key, scope)` markers. Reading the value through the typed
  accessor raises **`ConfigKeyUnset`** (loud). No consumer may catch it and substitute a default.
- Engines that need an unset key (for example a missing `sanity.floor_per_unit` when a category is
  evaluated) must treat the absence as a blocking precondition and surface it to the gate, not proceed.
- `sanity.floor_per_unit` / `ceiling_per_unit` being unset means "no absolute bound" only if the engine
  explicitly receives that signal from an accepted decision; it is never inferred from the absence.

### 4. Versioning: append-only, monotonic int + content hash

- Configuration is stored as an **append-only** sequence of versions per tenant. Rows are never updated
  or deleted (enforced by DB triggers in D2-03).
- `config_version`: a **monotonic integer per tenant**, starting at 1 for the seeded v1 defaults. Each
  applied change increments it by exactly 1. Versions are never reused or reordered.
- `content_hash`: `sha256` over the **canonical JSON** (RFC 8785 JCS, D2-06) of the *effective* values
  of the resolved configuration (all keys, unset keys included as `null`, provenance excluded). Hash
  reproducibility: the same effective values always produce the same hash, regardless of layer
  decomposition.
- An evaluation stores `(config_version, content_hash)`. Recomputing the effective config at that
  `config_version` must reproduce the hash exactly; a mismatch is a loud integrity error.

### 5. Closed enum: `money.supported_currencies` is non-configurable

- `money.supported_currencies` is the closed enum `EUR | USD | CNY`. It is **not** a configurable key:
  any patch touching it is rejected by the validator before a decision is created. It is mirrored by the
  DB enum `Currency` (D2-03).

### 6. Changes are signed decisions requiring immediate reauth

- `propose_change(tenant_id, patch, actor)` validates the patch (types, ranges, cross-field rules, closed
  enums, non-configurable keys), computes the candidate new version and its hash, and calls
  `DecisionPort.create_decision(type="config_change", subject_ref, payload)` (mirror of DEV-2's
  `apex.signing.api.create_decision`). This creates a `pending_signature` decision and returns its id;
  the API answers `202 Accepted` with that id.
- The payload contains the canonical patch, the base `config_version`, the candidate `config_version`
  and the candidate `content_hash`, so the signature binds the exact result.
- `apply_signed_change(decision_id)` calls `require_signed(decision_id)` (DEV-2). Only when it returns a
  signed decision is the new version appended. If it raises `PendingSignature`, nothing is written.
- Config changes require **immediate reauth** (ignore the signing window), per AGENTS.md DEV-2 task
  D2-09 item 5 ("threshold or weight changes").
- Concurrency: applying a change checks that `base config_version` is still current; if not, the change
  is rejected as stale and must be re-proposed (optimistic concurrency, no silent rebase).

### 7. Open TL questions (must be answered before this leaves Draft)

- **Q7 values**: the concrete values for keys currently "sin definir" are not invented here. Requested:
  `sanity.floor_per_unit`, `sanity.ceiling_per_unit` per category; `neg.target_discount` / `neg.max_discount`
  per category; `approval.threshold`, `approval.dual_control_above`, `signing.high_value_reauth_above`;
  `llm.roles.*` endpoints and models.
- **Q12 `sanity.on_insufficient_reference`**: §7 default is `gate`, with allowed values `gate | negotiate`.
  This draft ships `gate` (the spec default, the safe option). TL to confirm whether `negotiate` should
  ever be selectable per tenant, given spec §3.3.1 ("no se negocia a ciegas").
- **Q3 `seller.weights.*`**: pending DEV-3's ADR-304 (default weights per signal group). Shipped unset.
  Once ADR-304 is accepted, its values (not invented here) populate this section in a new v1 patch or v2
  default file.
- **Q13**: whether `global` defaults may be overridden per tenant at all for keys flagged as global-only
  in §7 (`fx.pivot`, `money.supported_currencies`). This draft treats `money.supported_currencies` as
  non-configurable and `fx.pivot` as overridable only by TL-approved change. TL to confirm.

### 8. Ports and boundaries

- Persistence: `ConfigRepository` Protocol (async). `InMemoryConfigRepository` is shipped now. The
  SQLAlchemy implementation is a **TODO pending D2-05** (`apex.db` does not exist yet). The
  CLI `python -m apex.tenant_config.load_defaults` runs against the repository and is a no-op with a
  warning in the DB-less path until D2-05 lands.
- Decisions: `DecisionPort` Protocol (async), a mirror of `apex.signing.api.create_decision` and
  `require_signed`. Tests use an in-memory fake. No file under `apex/signing/` is created by this lane.
- Clock: all timestamps (`resolved_at`) come from an injected `Clock` (`apex.common.clock`), never
  `datetime.now()` inside the engine.

## Consequences

- Engines never see a silent default: a missing business value fails loudly, which is intentional and
  forces the tenant to supply values before missions that depend on them can launch.
- Reproducibility is cheap: `(config_version, content_hash)` is stored with every evaluation.
- Every threshold change is a signed, reauth-gated decision, which is slower to change in practice. This
  is accepted by spec §7.
- Adds an explicit dependency on DEV-2's `create_decision` / `require_signed` signatures. Until they
  exist, the in-memory fake defines the contract and DEV-2 must match it (see the interface request
  in the PR description).

## Appendix A: Proposed OpenAPI snippet (for the contract PR owned by DEV-2)

Not committed by this lane (`/contracts/**` is owned by DEV-2). Proposed additions for
`/contracts/openapi.yaml`:

```yaml
paths:
  /v1/config/effective:
    get:
      operationId: getEffectiveConfig
      summary: Effective tenant configuration for a category
      parameters:
        - name: category
          in: query
          required: false
          schema: { type: string }
      responses:
        "200":
          description: Effective configuration with provenance
          content:
            application/json:
              schema: { $ref: "#/components/schemas/EffectiveConfig" }
        "401": { $ref: "#/components/responses/Problem" }
        "403": { $ref: "#/components/responses/Problem" }
  /v1/config/proposals:
    post:
      operationId: proposeConfigChange
      summary: Propose a configuration change (creates a pending signed decision)
      parameters:
        - $ref: "#/components/parameters/IdempotencyKey"
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/ConfigChangeRequest" }
      responses:
        "202":
          description: Pending signature decision created
          content:
            application/json:
              schema:
                type: object
                required: [decision_id, status]
                properties:
                  decision_id: { type: string }
                  status: { type: string, enum: [pending_signature] }
        "409": { $ref: "#/components/responses/Problem" }
        "422": { $ref: "#/components/responses/Problem" }
        "428": { $ref: "#/components/responses/ReauthRequired" }
components:
  schemas:
    EffectiveConfig:
      type: object
      required: [tenant_id, config_version, content_hash, resolved_at, values]
      properties:
        tenant_id: { type: string }
        category: { type: [string, "null"] }
        config_version: { type: integer, minimum: 1 }
        content_hash: { type: string, pattern: "^sha256:[0-9a-f]{64}$" }
        resolved_at: { type: string, format: date-time }
        values:
          type: object
          additionalProperties:
            type: object
            required: [value, status, layer]
            properties:
              value: {}
              status: { type: string, enum: [set, unset] }
              layer: { type: string, enum: [global, tenant, category] }
    ConfigChangeRequest:
      type: object
      required: [base_config_version, patch]
      properties:
        base_config_version: { type: integer, minimum: 1 }
        category: { type: [string, "null"] }
        patch:
          type: object
          description: Deep-merge patch. Explicit null unsets a key.
          additionalProperties: true
```

## Related

- PROMPT-IMPLEMENTACION.md §7 (configuration table), §3.3 (price sanity), §3.4 (seller confidence)
- AGENTS.md §0.5, §0.6, §3.5, §3.6, §4, §8
- ADR-003 (Ed25519 signatures), D2-06 (canonical JSON), D2-09 (decisions and reauth), D2-03 (append-only)
- Issue #48 (D4-03), blocked by #27 (D2-05)
- ADR-304 (seller weights, DEV-3, pending)
