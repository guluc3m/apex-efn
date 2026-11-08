# ADR-501: Deterministic negotiation guardrails

## Status

Proposed (DEV-5, D5-07a). Needs TL approval: it touches discount limits and counterparts (Q7, Q15).

## Context

Spec 3.6 lists hard guardrails for the negotiator: never exceed `max_discount` or the requested volume; no
prepayment, guarantees, terms or penalties without profile authorisation; maximum rounds and tokens per
conversation and messages per hour per account; escalate to a human on sensitive-data or off-platform
payment requests; and never accept a binding commitment ("el agente negocia, no compra"). Criterion 14
requires an adversarial suite to prove them.

The LLM drafts the messages (role `negotiator`). An LLM cannot be trusted to respect a number, so the
limits must be enforced by code that sits between the draft and the send.

## Decision

1. `apex.negotiation.guardrails` is pure and deterministic. It does no I/O and reads no clock or config by
   itself. `check_outgoing(text, limits, state, now=..., draft_tokens=...)` runs on every draft **before**
   it is sent. `check_incoming(text, supported_currencies=...)` runs on every seller message before the
   agent replies.
2. **Money in integer basis points.** `GuardrailLimits.max_discount_bp` is converted from the config
   fraction with `fraction_to_bp`, which rounds down. The price floor is
   `ceil(reference × (10000 − max_bp) / 10000)`, which rounds up. Both roundings make the guardrail stricter
   than the configured limit, never looser. The reference is the seller's opening quote in the negotiation
   currency. Every price in a draft is checked, not just the last one. A price in another currency is
   blocked.
3. **What is a price or a quantity.** A price is an amount next to a currency code or symbol. A quantity is
   a number next to a unit word (EN/ES/ZH). Bare numbers are neither. This keeps "round 2" or "net 30"
   from being read as prices.
4. **Severities.**
   - `block`: the draft is not sent. The engine may redraft or fall back to a template.
   - `escalate`: the agent stops and the conversation goes to the gate queue.
   - `notice`: the agent continues but must act. For closing pressure it summarises and never accepts. For
     an unsupported currency it asks for EUR, USD or CNY (spec 3.6 steps 6 and 8).
5. **Patterns are conservative.** A false positive costs a redraft or a human review. A false negative
   could cost a breach. Patterns are table-tested in EN, ES and ZH, and the adversarial suite (D5-09) runs
   them against the mock marketplace personas.
6. **Limits with no default.** `GuardrailLimits` has no defaults, and the caller builds it from tenant
   config and the buyer profile. If `neg.max_discount` is unset (Q7), the negotiation does not start. These
   limits have no config key yet: tokens per conversation, messages per hour per account, maximum message
   length, and authorised counterparts. They are requested from DEV-4 and the TL in the issue tracker.
7. **Prices are not judged here.** Seller prices are extracted and handed to DEV-3's `sanity.check`. An
   `atypical` or `implausible` result stops the negotiation (criterion 13). That wiring is in the
   negotiation engine (D5-07b), not in this module.

## Consequences

- The guardrails can be tested exhaustively without an LLM, a browser or a database, and they are a
  coverage-gated module (`apex/negotiation/guardrails*`, 80%).
- The negotiator prompt can be changed freely. A prompt regression cannot breach a limit, it can only
  cause more redrafts or escalations.
- Regex detection will miss unusual phrasings. Mitigations: semi-automatic mode in Phase 1 (a human
  approves every send), escalation on doubt, and growing the pattern tables from the adversarial suite and
  from real transcripts.

## Related

- PROMPT-IMPLEMENTACION.md 3.1, 3.6, 7, 9 (criteria 13, 14)
- AGENTS.md D5-07, D5-09, section 8 Q7 and Q15
- ADR-500 (browser stack), issue #96 (tenant config Q7)
