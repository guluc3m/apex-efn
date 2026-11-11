"""The §8 API surface (PROMPT-IMPLEMENTACION.md §8), as (method, path) pairs under /v1.

Path parameters use ``{id}`` (``{platform}`` for webhooks), as in the spec's ``{id}`` notation.
``POST /v1/keys/me`` is in §8 as "registro de nueva". The config routes are DEV-4's own (D4-03) and
are not in §8 text, so they are kept in a separate set until a contract PR adds them.
"""

SPEC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/v1/onboarding/sessions"),
        ("POST", "/v1/onboarding/{id}/financial-csv"),
        ("POST", "/v1/onboarding/{id}/financial-csv/activate"),
        ("POST", "/v1/sourcing-requests"),
        ("POST", "/v1/missions"),
        ("GET", "/v1/missions/{id}"),
        ("GET", "/v1/missions/{id}/events"),
        ("GET", "/v1/missions/{id}/offers"),
        ("GET", "/v1/sellers/{id}/confidence"),
        ("POST", "/v1/sellers/{id}/confidence/recompute"),
        ("GET", "/v1/dashboard/deals"),
        ("POST", "/v1/dashboard/deals/{id}/actions"),
        ("GET", "/v1/gate/queue"),
        ("POST", "/v1/gate/queue/{id}/actions"),
        ("POST", "/v1/negotiations/{id}/takeover"),
        ("POST", "/v1/negotiations/{id}/resume"),
        ("POST", "/v1/negotiations/{id}/abort"),
        ("GET", "/v1/missions/{id}/recommendation"),
        ("POST", "/v1/signing-sessions"),
        ("GET", "/v1/signing-sessions/{id}"),
        ("DELETE", "/v1/signing-sessions/{id}"),
        ("POST", "/v1/decisions"),
        ("POST", "/v1/decisions/{id}/sign"),
        ("POST", "/v1/decisions/{id}/verify"),
        ("GET", "/v1/keys/me"),
        ("POST", "/v1/keys/me"),
        ("POST", "/v1/keys/{id}/revoke"),
        ("GET", "/v1/audit/verify"),
        ("GET", "/v1/audit"),
        ("POST", "/v1/webhooks/platforms/{platform}"),
    }
)

# Routes that answer real responses instead of 501, so the stub check below skips them; their own tests
# cover behaviour. DEV-4: D4-03 config, D4-08 sourcing and missions. DEV-5: D5-08 negotiation controls.
IMPLEMENTED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/v1/sourcing-requests"),
        ("POST", "/v1/missions"),
        ("GET", "/v1/missions/{id}"),
        ("GET", "/v1/missions/{id}/events"),
        ("POST", "/v1/onboarding/sessions"),
        ("POST", "/v1/onboarding/{id}/financial-csv"),
        ("POST", "/v1/onboarding/{id}/financial-csv/activate"),
        ("POST", "/v1/negotiations/{id}/takeover"),
        ("POST", "/v1/negotiations/{id}/resume"),
        ("POST", "/v1/negotiations/{id}/abort"),
        ("GET", "/v1/audit"),
        ("GET", "/v1/audit/verify"),
    }
)

# Routes added by DEV-4 for the config service (D4-03). Not in §8 text: pending a contract PR.
CONFIG_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/v1/config/effective"),
        ("POST", "/v1/config/proposals"),
    }
)

# Routes DEV-4 added that section 8 does not list (progressive form backend for D4-07). Same situation as the
# config routes: they need a contract PR once /contracts exists.
DEV4_EXTRA_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("PATCH", "/v1/onboarding/sessions/{id}"),
        # Read a session back and find the current one (D6-377-contract).
        ("GET", "/v1/onboarding/sessions"),
        ("GET", "/v1/categories"),
        ("GET", "/v1/missions/{id}/recommendation/export"),
        ("GET", "/v1/onboarding/sessions/{id}"),
        ("GET", "/v1/onboarding/{id}/financial-csv/{import_id}"),
        ("POST", "/v1/onboarding/{id}/financial-csv/mapping"),
        # Read a decision and its canonical payload before signing (D6-151-contract).
        ("GET", "/v1/decisions/{id}"),
        # IntakeAgent chat (D6-04-contract, D4-07b).
        ("GET", "/v1/onboarding/sessions/{id}/messages"),
        ("POST", "/v1/onboarding/sessions/{id}/messages"),
        # Approvals inbox over decisions (D6-165-contract).
        ("GET", "/v1/approvals"),
        ("GET", "/v1/approvals/{id}"),
        # Missions list/lifecycle, config history and ranking profiles (issues #302, #303, #306).
        ("GET", "/v1/missions"),
        ("POST", "/v1/missions/{id}/pause"),
        ("POST", "/v1/missions/{id}/resume"),
        ("POST", "/v1/missions/{id}/cancel"),
        ("GET", "/v1/config/versions"),
        ("GET", "/v1/profiles"),
        # Deal by id and dashboard counters (issue #305).
        ("GET", "/v1/dashboard/deals/{id}"),
        ("GET", "/v1/dashboard/summary"),
    }
)

# Routes DEV-5 added that section 8 does not list: reading a negotiation, its transcript and the
# semi-automatic approval loop (D5-07c). Declared in contracts/openapi.yaml; they answer 501 until D5-07c
# implements them.
DEV5_EXTRA_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/v1/negotiations/{id}"),
        ("GET", "/v1/negotiations/{id}/messages"),
        ("POST", "/v1/negotiations/{id}/messages"),
        ("POST", "/v1/negotiations/{id}/approve"),
        ("POST", "/v1/negotiations/{id}/reject"),
        ("POST", "/v1/negotiations/{id}/reopen"),
    }
)

# Routes DEV-2 added that section 8 does not list: logout on every device (issue #272).
DEV2_EXTRA_ROUTES: frozenset[tuple[str, str]] = frozenset({("DELETE", "/v1/signing-sessions")})

# The exact-set check covers both. The 501 stub check covers only SPEC_ROUTES minus IMPLEMENTED_ROUTES.
EXPECTED_ROUTES: frozenset[tuple[str, str]] = (
    SPEC_ROUTES | CONFIG_ROUTES | DEV2_EXTRA_ROUTES | DEV4_EXTRA_ROUTES | DEV5_EXTRA_ROUTES
)
