# ADR-504: Human controls and anti-abuse for negotiations (digest 1)

## Status

Proposed (DEV-5, D5-08). `TL approval: no`.

## Context

Spec 3.6 makes the negotiation semi-automatic in Phase 1: a human can take the chat at any moment, and
the agent must stop sending. Spec 5.9 adds our own anti-abuse rules: a rate limit per seller account and a
ban on contacting the same seller from simultaneous missions. ADR-502 already put the playbook, the
guardrails and the single send path in the engine; the human controls existed as methods but had no HTTP
face, and nothing prevented two missions from opening two chats with one seller.

## Decision

1. **One seam for the controls.** `apex.negotiation.api` exposes `takeover`, `resume` and `abort` (the
   names AGENTS.md section 4 gives DEV-4) and `NegotiationControlService`, which
   `POST /v1/negotiations/{id}/takeover|resume|abort` uses. The HTTP layer and the mission graph therefore
   cannot drift apart.
2. **The engine stays the only sender.**
   - `take_over` refuses a terminal negotiation, drops the pending draft and sets `human_in_control`.
     `advance` returns without reading or sending, and `approve` refuses, while a human holds the chat.
     The guardrail (`HUMAN_IN_CONTROL`) also blocks any send that tried to bypass both.
   - `resume` requires a previous takeover (`not_in_human_control` otherwise) and hands control back.
   - `abort` is terminal and idempotent: the first reason wins, later calls return the same state.
3. **One active negotiation per seller, across missions.** A new `SellerGuard` port claims
   `(tenant_id, platform, seller_id)` before the chat is opened, is idempotent for the holder (a retried
   start keeps working), stays held while a human is in control and is released on every terminal outcome
   (agreed, no agreement, escalated, anomalous price, aborted).
   - A refused claim raises `seller_busy`. The graph adapter (`EngineNegotiationPort`) turns it into a
     terminal `escalated` result with `reason="seller_busy"` and the id of the negotiation that holds the
     seller, so the offer reaches the human gate instead of opening a second conversation.
   - Tenants are independent: the key includes the tenant, and the store is tenant-scoped like everything
     else (RLS, D2-04).
4. **Per-seller rate limit with the configured number, not a new one.** `neg.max_messages_per_hour_per_account`
   (ADR-900 Q7) is applied to two scopes: the platform account (as before) and the seller account, across
   missions. A hit is `seller_rate_limited`, mapped to the contract's `message_rate`. Rate limiting parks a
   message and retries it later; it never fails a negotiation (same rule as the account limit).
5. **Timestamped guardrail hits.** `guardrail_events` records `{code, at}` with the injected clock, so the
   contract's `GuardrailHit{code, at}` is answered with a real reading instead of a made-up one.
   `apex.negotiation.api.to_contract` maps the internal outcomes to the public `NegotiationState` and the
   internal hit codes to the closed `GuardrailCode`, deduplicated per code (the full sequence stays in the
   session and the audit log). Internal diagnostics (`draft_failed`, `extraction_not_grounded`,
   `draft_off_plan`, `empty_message`) have no public equivalent and are not shown in this view.
6. **Public state mapping.**

   | Internal outcome | Public `state` |
   |---|---|
   | `in_progress`, `awaiting_seller` | `running` |
   | `awaiting_human_approval` | `awaiting_approval` |
   | `agreed`, `no_agreement` | `completed` |
   | `escalated`, `stopped_anomalous_price` | `escalated` |
   | `aborted` | `aborted` |
   | any non-terminal outcome with `human_in_control` | `human_control` |

7. **The control endpoints work before the graph is wired.** The router's default dependency builds an
   in-process engine over the in-memory store and deliberately unwired drafting/sending collaborators
   (they raise loudly if reached). It answers `404` for ids it does not know. When DEV-4 wires the mission
   graph it injects the shared engine through `get_negotiation_control`, as the gate router already does.

## Consequences and limits

- `InMemorySellerGuard` and `InMemorySellerSendLog` are process-local, like the engine's per-negotiation
  lock. A multi-worker deployment needs Redis or a DB uniqueness constraint (D2-05) so two workers cannot
  claim the same seller or exceed the hourly cap. That is an interface to agree with DEV-2, not a change to
  this decision.
- A negotiation that waits for the seller or for a human keeps the seller claimed. A stuck negotiation
  therefore blocks a new one with that seller until somebody aborts it; the gate queue owns that decision.
- No RBAC yet: the tenant comes from the dev-only header until D1-05, and the `buyer|admin|owner` check on
  these calls lands with it. The contract already declares the `403`.
- The contract has no `off_platform_contact` guardrail code, so an escalation caused by an off-platform
  contact request shows as `escalated` with the code only in `stop_reason`. Proposing the enum member is a
  contract change for DEV-2.
- The `Negotiation` view does not carry the transcript; the takeover panel (D6-07a) needs the negotiation
  messages endpoint that the contract does not have yet.

## Related

- PROMPT-IMPLEMENTACION.md 3.6, 5.9; AGENTS.md D5-08 and section 4
- ADR-403, ADR-500, ADR-501, ADR-502, ADR-900; issue #67, unblocks #90
