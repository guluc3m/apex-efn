# Runbook: audit chain broken

**Owner:** DEV-2 (D2-10). **Applies to:** `GET /v1/audit/verify` returns `valid: false`.

Each tenant has its own chain: `hash = SHA-256(JCS(record))`, where the record includes `prev_hash`; `seq` starts
at 1 with no gaps and the first event chains to 64 zeros. The head is anchored to S3 Object Lock (compliance
mode), so the anchor cannot be rewritten before its retention ends.

## Read the result

- `first_broken_seq`: the first event that fails (a bad hash, payload hash, link or a gap in `seq`).
- `valid: false` with `anchored_head_hash` set and `first_broken_seq` equal to the anchored seq: the chain is
  self-consistent but the event at the anchored `seq` no longer has the anchored hash. Someone **rewrote** history
  and recomputed the hashes. Treat as an incident.

## Steps

1. Do not fix rows. The tables are append-only (triggers block UPDATE and DELETE); an edit that got through
   means someone with superuser access bypassed the triggers. Freeze that access.
2. Preserve evidence: dump `audit_events` for the tenant and keep the anchor objects of that tenant
   (`anchors/<tenant_id>/`).
3. Compare with the most recent database backup and the anchors to find the earliest good `seq`. Everything from
   `first_broken_seq` on is untrusted until explained.
4. Check the signature chain too: `POST /v1/decisions/{id}/verify` on affected decisions. Signed decisions carry
   their own chain and stay verifiable independently.
5. Open a security incident with the tenant id, `first_broken_seq`, the verify output and the time it was detected.

A gap in `seq` with a valid remainder means a row was deleted. A single changed field means an update. Neither
is ever a normal operation.

## Do not

Re-anchor a broken chain (`anchor_head` refuses it on purpose), recompute hashes, or delete anchors.
