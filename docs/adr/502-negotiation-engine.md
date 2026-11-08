# ADR-502: Negotiation engine: playbook, untrusted LLM, sanity re-check and semi-automatic sends

## Status

Proposed (DEV-5, D5-07b). Needs TL approval (D5-07 is `TL approval: yes`).

## Context

Spec 3.6 defines the strategy (steps 1-8) and the hard guardrails. ADR-501 put the guardrails in pure
functions. ADR-900 fixed the contract with the mission graph: a closed outcome enum, a unit `price_minor`
only for `agreed`, and an attempt-scoped idempotency key. Phase 1 is semi-automatic: every message waits
for a human approval (spec 10).

## Decision

1. **The playbook decides, the LLM words.** `apex.negotiation.playbook.decide` picks the next
   `Plan(intent, price_minor)`. The intents are `open`, `request_price`, `anchor`, `counter`,
   `request_currency` and `summary`. The buyer anchors at the floor allowed by `max_discount` and climbs
   a ladder with non-increasing increments up to `target_discount`. Two rounds are kept outside the ladder:
   the opening and the written summary. When the seller quotes at or below the target price, the agent
   sends a written summary and asks for written confirmation. The outcome becomes `agreed`, which means
   "ready for a human decision", never a purchase.
2. **The LLM is untrusted on both sides.**
   - **Drafts.** A draft must state exactly the planned price, or no price when none is planned
     (`plan_matches`). It must also pass `check_outgoing`. After `max_drafts` failures, or when the LLM is
     unavailable, the engine falls back to deterministic templates that pass the same checks.
   - **Extraction** (`chat_structured`, role `negotiator`). The result is accepted only when it is
     _grounded_: the same amount and currency must appear literally in the seller text. Otherwise the
     engine uses the deterministic parser (lowest price in the negotiation currency).
3. **Single send path.** `_send` re-runs `check_outgoing` right before the transport call, so an approved
   draft cannot be sent if the situation changed after approval. The situation includes rounds, tokens,
   hourly rate, a human in control and the limits.
4. **Seller turns.**
   - `check_incoming` escalations (sensitive data, off-platform payment or contact) stop the agent with
     `escalated`. Nothing more is sent.
   - Closing pressure and unsupported currencies are notices, recorded on the negotiation. For an
     unsupported currency the playbook asks for a quote in the negotiation currency (step 8).
5. **Sanity re-check (criterion 13).** Every accepted quote goes through `SanityRecheck` (a port to DEV-3's
   `sanity.check`; the adapter converts to EUR landed cost per unit). `atypical` or `implausible` stops
   the negotiation with `stopped_anomalous_price`. The graph routes that to the gate.
6. **Semi-automatic by default.** Drafts are parked as `pending` with outcome `awaiting_human_approval`.
   - `approve(draft_id)` sends the draft after the guardrails run again.
   - `reject(draft_id)` replaces it with the template.
   - `take_over` drops the pending draft, and the agent sends nothing until `resume`.
   - `abort` is terminal and idempotent.

   Autonomous mode (Phase 2, `negotiation.autonomous_send`) uses the same path without the approval
   step. A rate-limited message is parked and retried, never failed.

7. **Counterparts (Q15).** `NegotiationParams` refuses any counterpart other than `higher_volume` and
   `framework_contract` in Phase 1, even if a profile lists more.
8. **Graph contract.** `EngineNegotiationPort.negotiate(offer, tenant_id, idempotency_key)` starts the
   negotiation on the first call and advances it on later calls with the same key. It returns
   `NegotiationResult{outcome, negotiation_id, price_minor, currency, quantity, reason}`. Non-terminal
   outcomes (`awaiting_human_approval`, `awaiting_seller`, `in_progress`) must not be cached by the
   graph's effect ledger.
9. **Persistence and transport are ports.** `NegotiationStore`, `AccountSendLog` and `ChatTransport`
   have in-memory or test implementations here. The real ones come with the data layer (D2-05) and the
   browser worker (D5-01, D5-03). Transcripts and screenshots in S3, plus the approve-send HTTP
   endpoint (contract PR after D2-01), are follow-ups in D5-07c.

## Consequences

- Criterion 13 and the core of criterion 14 are testable without an LLM, a browser or a database. The
  adversarial suite (D5-09) adds the mock-marketplace personas end to end.
- Prompts live in `apex/negotiation/llm.py` with versions `negotiator_draft@v1` and
  `negotiator_extract@v1`. They move to DEV-4's prompt registry when D4-05 merges.
- The engine adds `awaiting_seller` and `in_progress` to the outcome enum as non-terminal states. The
  graph treats both like `awaiting_human_approval` (interrupt and poll).

## Related

- PROMPT-IMPLEMENTACION.md 3.6, 9 (criteria 13, 14), 10
- ADR-403, ADR-500, ADR-501, ADR-900; issues #66, #115; PR #112
