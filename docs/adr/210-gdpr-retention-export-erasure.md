# ADR-210: GDPR retention, subject export and erasure that keeps the chains verifiable

## Status

Proposed (needs Tech Lead approval, D2-12)

## Context

Spec 5.9 requires retention per data class, export per data subject and erasure. Two things fight each other:
the signature chain (ADR-209) and the audit chain (D2-10) are append-only and hash-linked, so deleting or
editing any row breaks `verify`; and GDPR art. 17 lets a person ask for their personal data to go.

What is personal data here: `users.email`, `users.display_name`, `users.external_subject`,
`signing_sessions.device_fingerprint_ref` and `signing_keys.label`. Everything the chains hash refers to the
person only by the opaque `user_id` (a pseudonym) plus public keys and hashes.

## Decision

1. **Chains are never edited.** Erasure does not touch `signatures`, `decisions`, `audit_events` or the S3
   anchors. A signed record must stay verifiable for the legal-obligation basis (art. 17(3)(b) and (e): purchase
   decisions are accounting records and are needed for legal claims).
2. **Rule for authors:** no direct personal data (email, name, free text typed by a person) goes into a decision
   payload or an audit payload. Only ids, hashes and business values. A test would be the place to enforce it
   for new event types; this ADR makes it a review rule.
3. **Erasure = pseudonymisation of the identity row** (`apex.gdpr.erase_subject`): `email` becomes
   `erased+<user_id>@invalid`, `display_name` becomes `erased user`, `external_subject` becomes null, the
   device fingerprints of the user's sessions are replaced by `erased`, key labels are cleared, every active
   session is revoked and every active key is revoked (reason `gdpr_erasure`). The `user_id` stays so past
   signatures still resolve to "a user who has since been erased". Erasing the Keycloak account is an ops
   step (DEV-1 runbook), not done by the orchestrator.
4. **Export** (`apex.gdpr.export_subject`): one JSON document with the identity row, memberships, keys (public
   part), sessions, and references (ids, type, timestamps) to the decisions signed and audit events performed
   by the subject. Read-only, no secrets.
5. **Retention** is config, not code: `gdpr.retention_days.<class>` per data class. **Unset means keep**; this
   ADR does not invent periods. `apex.gdpr.purge_session_fingerprints(cutoff)` is the one automatic purge
   (ended sessions older than the cutoff lose their fingerprint). Classes that live in S3 (CSV originals,
   transcripts, screenshots) are purged by lifecycle rules in infra (DEV-1), driven by the same keys.
6. Erasure and export are operator actions on a request. They are not exposed as public endpoints in this task;
   a contract PR can add them once the TL says who may call them.

## Consequences

- The audit/signature chains keep verifying after any erasure (tested).
- A person's name cannot be recovered from the DB after erasure, but their id can still be linked to old
  decisions. That is the intended trade-off.
- If a future event type needs to carry personal text, it must hash it and store the text elsewhere.

## Related

- ADR-209 (signatures chain), D2-10 (audit chain), issue #34, spec 5.9.
