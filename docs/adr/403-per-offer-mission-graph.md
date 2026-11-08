# ADR-403: Per-offer mission graph, signed gates and idempotent effects

## Status

Accepted in substance by the Tech Lead in ADR-900 (items under "ADR-403"); the PR review lists the changes that were required before approval. D4-06 is `TL approval: yes`, so the TL merges.

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

## Decisions from the Tech Lead (ADR-900)

1. After a pre-stage unblock the offer still runs the financial check before negotiating.
2. A price that becomes anomalous after negotiation needs a **new** signed unblock. The decision key is
   `(offer, stage, attempt)` and the signed payload must carry the same `stage` and `attempt`, so an earlier
   unblock cannot authorize a later gate.
3. `financials_stale` and `fx_provisional` are enforced by D4-11 at purchase time. The graph also never
   purchases an `out_of_budget` offer: it stays `approved` with `purchase_blocked=["out_of_budget"]`.
4. Negotiation contract with DEV-5:
   - `NegotiationResult.outcome` is a closed enum (`agreed`, `no_agreement`, `escalated`,
     `stopped_anomalous_price`, `awaiting_human_approval`, `awaiting_seller`, `aborted`, `in_progress`); it
     carries `negotiation_id`, `price_minor` (**unit** price, only for `agreed`), `currency` and `quantity`.
   - `escalated` and `stopped_anomalous_price` go to the gate; `no_agreement` and `aborted` reject.
   - Non-terminal outcomes (`awaiting_human_approval`, `awaiting_seller`, `in_progress`) interrupt the graph,
     are never cached by the ledger, and the next call uses the **same** idempotency key. The wait is its own
     node because LangGraph replays a node from the start on resume.
   - Idempotency key: `negotiate:<subject_ref>:<attempt>`. A signed `renegotiate` at the post gate starts the
     next attempt, up to `gate.max_renegotiations` (read from config, fails loudly when unset).
5. The negotiated price is converted to EUR per unit by a `PriceNormalizer` port (DEV-3 FX) before the
   sanity re-check. An unblock is refused when the negotiation has no agreed price.

## Related

- Spec section 4, criteria 11, 12, 17, 18. Issue #92 (signing/audit interface), #51 (D4-06).
- ADR-400 (tenant config), ADR-401 and ADR-402 (workers, supervisor) are DEV-4 ADRs on other branches.
