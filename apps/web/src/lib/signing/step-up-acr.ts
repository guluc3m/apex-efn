/**
 * Keycloak ACR value requested for a signing step-up (ADR-900 Q11).
 *
 * It is mapped to Level of Authentication 2 in `infra/keycloak/realm-apex.json` via the realm
 * attribute `acr.loa.map` (`{"urn:apex:loa:2": 2}`). The same value is requested from Keycloak with
 * `acr_values` in `app/api/auth/signin/route.ts`, so there is one string in one place: a mismatch
 * between the request and the realm mapping would silently downgrade the step-up.
 */
export const STEP_UP_ACR = 'urn:apex:loa:2'
