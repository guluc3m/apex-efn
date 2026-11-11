# Runbook: signing session blocked

**Owner:** DEV-2 (D2-10). **Applies to:** a signer gets `428 {error: "reauth_required", reason}` and cannot sign.

The window is fixed (`expires_at = auth_at + signing.session_minutes`) and is never extended by signing. A 428 is
the system working as designed, not an outage. Read `reason` first.

| `reason` | Meaning | Fix |
|---|---|---|
| `session_missing` / `session_expired` | No session, or the fixed window ended | Sign in with the passkey again (opens a new session) |
| `session_exhausted` | `max_decisions_per_session` reached | Open a new session |
| `high_value_decision` / `immediate_reauth_required` / `step_up_required` | Amount above `signing.high_value_reauth_above`, or a decision type that always needs a fresh step-up | Re-authenticate for this decision; the window does not apply |
| `key_revoked` / `key_rotated` | The key of the session was revoked or rotated, which ends its sessions | Enroll a key (see `key-loss.md`) and open a session |
| `device_mismatch` | Device fingerprint changed; the session was killed | Re-authenticate on the device that holds the key. Repeated mismatches suggest a stolen session: tell security |
| `network_anomaly` | ASN or country jump inside the session | Re-authenticate. If the user did not travel, treat as a possible hijack |
| `risk_flagged` / `session_revoked` | The GateAgent called `mark_session_risky()`, or the session was ended on purpose | Re-authenticate; review the gate event in the audit log (`GET /v1/audit?subject_ref=...`) |

## If a user is blocked and none of the above explains it

1. Check the `Keycloak` step-up: the token must carry a recent `auth_time` and the required ACR.
2. Check the browser supports Ed25519 in WebCrypto. If not, signing is blocked on purpose and there is no
   server-side fallback (ADR-203). Use a supported browser.
3. A `viewer` never signs (403, not 428).

Never extend a session by hand in Redis or the database, and never sign on behalf of a user. Escalate to DEV-2 with
the decision id and the `reason`.
