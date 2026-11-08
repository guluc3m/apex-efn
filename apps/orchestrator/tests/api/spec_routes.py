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

# Routes added by DEV-4 for the config service (D4-03). Not in §8 text: pending a contract PR.
CONFIG_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/v1/config/effective"),
        ("POST", "/v1/config/proposals"),
    }
)

EXPECTED_ROUTES: frozenset[tuple[str, str]] = SPEC_ROUTES | CONFIG_ROUTES
