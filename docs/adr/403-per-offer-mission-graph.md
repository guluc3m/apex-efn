# ADR-403: Per-offer mission graph, signed gates and idempotent effects

## Status

Proposed (D4-06 is `TL approval: yes`; needs tech lead sign-off before merge).

## Context

Spec section 4 defines a per-offer state machine (`discovered -> ... -> purchased`). Spec rules that must
hold: trust and sanity checks come before any negotiation (criterion 12); every relevant transition emits a
service-signed audit event; human gates use interrupts that resume only after `require_signed()` succeeds; a
resumed mission never duplicates messages or signatures.

The scaffold had one mission-level graph with stub nodes. Real work happens per offer, and offers wait on
humans for hours or days, so each offer needs its own resumable thread.

## Decision

1. **One LangGraph thread per offer**, thread id `<mission_id>:<offer_id>`. The mission-level fan-out
   (planning, scraping, spawning one offer thread per enriched offer) belongs to D4-08/D4-09. This task
   builds the offer graph only; the old scaffold graph is left in place until then.
2. **The transition table is code** (`offer_state.ALLOWED`). Every node moves status through one
   `move()` that validates against it. Skipping a step raises `InvalidTransition`. `gate_pending` is the
   "(gate)" node of the spec diagram; discards end in `rejected`.
3. **Negotiation is gated by structure and by a check.**
   - `negotiate` has exactly one incoming edge, from `check_financial`. `check_financial` is reached only from
     the router (route = negotiate **and** price band `normal`) or from `gate_wait` after a signed unblock.
   - The router refuses `negotiate` for price bands `atypical`, `implausible` and `insufficient_reference`
     even if the combiner returns it, and routes to the gate with reason
     `graph_override:price_band_requires_signed_unblock`. This protects against a combiner bug.
   - `negotiate` raises `NegotiationNotCleared` if entered without `negotiation_cleared`.
4. **Human gates are LangGraph `interrupt()` calls inside a loop around `require_signed()`.** Resuming with an
   unsigned decision pauses again. After a signature, the graph checks that the decision type and
   `subject_ref` match the offer and that the signed payload's `action` is what the node expects
   (`unblock`, or `approve`/`reject`). The signed payload is the one built by the graph, containing the
   price sanity check, seller confidence (band, score, model version), financial fit and `config_version`.
5. **Idempotent effects through an `EffectLedger`.** Decision creation, service signatures, audit events,
   enrichment, financial fit and negotiation run through `ledger.once(key, effect)`, keyed by offer and step.
   A node re-run after a crash or resume replays the stored result. The ledger is a port; the Postgres
   implementation belongs to the DEV-2 data layer (D2-05). `InMemoryEffectLedger` serves tests.
6. **`purchased` is reached only through `approved`**, and `purchase` re-verifies the signed approval with
   `require_signed()` instead of trusting state.
7. **Postgres checkpointer** (`langgraph-checkpoint-postgres`) with its own tables. Not Prisma-owned and not
   under RLS; it stores plain JSON keyed by thread id. DEV-1/DEV-2 to confirm the DSN, role and retention.
8. **All collaborators are ports** (`apex.agents.ports`): trust, sanity, gate combiner, finance, negotiation,
   scoring, decisions (`create_decision`, `require_signed`, `sign_service_event`, issue #92 shape), audit.
   Band enums are local copies of the spec vocabulary until the DEV-3 domain types merge.

## Consequences

- Criterion 12 is testable without the real engines: the negotiator counter stays 0 for every anomalous band
  combination, with and without a buggy combiner.
- A worker restart resumes every offer from its checkpoint without repeating effects, provided the ledger
  is durable. With the in-memory ledger a restart can repeat effects, so production must not use it.
- Two decision types are used now: `gate_unblock` and `deal_action`. DEV-2 must accept them (issue #92).
- Reject-by-human and expiry both end in `rejected`; the reason distinguishes them.

## Open questions for the tech lead

1. After a signed unblock at the *pre* stage, should the offer still run the financial check before
   negotiating? The graph does (it always does).
2. After negotiation, a price that returns to `normal` goes straight to scoring; one that is `atypical` goes to
   the gate again. Confirm that a second signed unblock is required rather than reusing the first.
3. `financials_stale` and `fx_provisional` blocks are enforced at purchase time by the gate/dashboard
   (D4-11), not inside this graph. Confirm.

## Related

- Spec section 4, criteria 11, 12, 17, 18. Issue #92 (signing/audit interface), #51 (D4-06).
- ADR-400 (tenant config), ADR-401 and ADR-402 (workers, supervisor) are DEV-4 ADRs on other branches.
