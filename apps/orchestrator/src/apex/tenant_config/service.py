"""TenantConfigService: effective resolution, validated change proposals and signed application.

ADR-400. Every method is async (ports are async). Time comes from the injected ``Clock``; nothing here
calls ``datetime.now()``.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import ValidationError

from apex.tenant_config.defaults import DEFAULT_PATH, load_global_layer, scope_of
from apex.tenant_config.errors import (
    ConfigValidationError,
    ContentHashMismatchError,
    NonConfigurableKeyError,
    StaleBaseVersionError,
)
from apex.tenant_config.models import TenantConfig
from apex.tenant_config.ports import (
    Clock,
    ConfigRepository,
    ConfigVersionRecord,
    DecisionPort,
)
from apex.tenant_config.resolver import (
    EffectiveConfig,
    FloatInConfigError,
    Layer,
    ResolvedValue,
    assert_no_floats,
    content_hash,
    deep_merge,
    flatten,
)

DECISION_TYPE_CONFIG_CHANGE: Final[str] = "config_change"

NON_CONFIGURABLE_PATHS: Final[frozenset[str]] = frozenset({"money.supported_currencies"})
"""Closed enum keys (ADR-400 §5). Any patch touching them is rejected before a decision exists."""

CATEGORY_KEY: Final[str] = "categories"
"""Tenant-layer key holding per-category overrides: ``{"categories": {"<cat>": {...}}}``."""


class TenantConfigService:
    def __init__(
        self,
        repository: ConfigRepository,
        decisions: DecisionPort,
        clock: Clock,
        *,
        defaults_path: Any = DEFAULT_PATH,
    ) -> None:
        self._repo = repository
        self._decisions = decisions
        self._clock = clock
        self._defaults_path = defaults_path
        self._scopes: dict[str, str] = scope_of(defaults_path)
        self._global_version, self._global = load_global_layer(defaults_path)

    # ------------------------------------------------------------------ resolution

    async def _tenant_patch(self, tenant_id: str) -> tuple[int, dict[str, Any]]:
        """Accumulated tenant-layer patch and its current ``config_version``.

        A tenant with no stored record is the seeded v1 baseline: version 1 with an empty patch
        (ADR-400 §4). ``effective`` and ``propose_change`` must agree on this number.
        """
        latest = await self._repo.latest_version(tenant_id)
        if latest is None:
            # No stored baseline: the seed (load_defaults) must run first. Reads still resolve to the
            # global defaults at version 1; changes are refused by the caller (see _require_baseline).
            return self._global_version, {}
        return latest.config_version, _copy_json(latest.values)

    async def _require_baseline(self, tenant_id: str) -> None:
        if await self._repo.latest_version(tenant_id) is None:
            raise ConfigValidationError(
                f"tenant {tenant_id} has no stored config baseline; run load_defaults first"
            )

    async def effective(self, tenant_id: str, category: str | None = None) -> EffectiveConfig:
        """Resolve global → tenant → category, with per-key provenance and integrity fields."""
        tenant_version, tenant_patch = await self._tenant_patch(tenant_id)
        category_patch: dict[str, Any] = {}
        if category is not None:
            cats = tenant_patch.get(CATEGORY_KEY, {})
            category_patch = _copy_json(cats.get(category, {})) if isinstance(cats, dict) else {}

        tenant_only = {k: v for k, v in tenant_patch.items() if k != CATEGORY_KEY}
        after_tenant = deep_merge(self._global, tenant_only)
        effective_plain = deep_merge(after_tenant, category_patch)

        # Validate the fully merged result. Unset keys (None) are allowed; wrong types/ranges are not.
        typed = _validate_merged(effective_plain)

        effective_flat = flatten(effective_plain)
        tenant_flat = flatten(tenant_only)
        cat_flat = flatten(category_patch)
        values: dict[str, ResolvedValue] = {}
        for path, value in effective_flat.items():
            if path in cat_flat:
                layer = Layer.CATEGORY
            elif path in tenant_flat:
                layer = Layer.TENANT
            else:
                layer = Layer.GLOBAL
            values[path] = ResolvedValue(path=path, value=value, layer=layer, unset=value is None)

        version = tenant_version  # already the seeded baseline (1) when the tenant has no record
        # No category: the hash is the version identity (category overrides included). With a category it
        # hashes exactly what that category sees, plus the version it came from.
        digest = (
            _version_hash(self._global, tenant_patch)
            if category is None
            else content_hash({"category": category, "view": _plain(effective_plain)})
        )
        return EffectiveConfig(
            tenant_id=tenant_id,
            category=category,
            config_version=version,
            content_hash=digest,
            resolved_at=self._clock.now(),
            values=values,
            typed=typed,
        )

    async def history(self, tenant_id: str) -> list[ConfigVersionRecord]:
        """Stored versions, newest first."""
        rows = await self._repo.list_versions(tenant_id)
        return sorted(rows, key=lambda r: r.config_version, reverse=True)

    async def categories(self, tenant_id: str) -> list[str]:
        """Categories that have an override in the latest tenant version, sorted."""
        latest = await self._repo.latest_version(tenant_id)
        cats = latest.values.get(CATEGORY_KEY, {}) if latest else {}
        return sorted(cats) if isinstance(cats, dict) else []

    async def verify_version(self, tenant_id: str, config_version: int) -> None:
        """Recompute a stored version's hash; raise on mismatch (ADR-400 §4 reproducibility)."""
        record = await self._repo.get_version(tenant_id, config_version)
        if record is None:
            raise ConfigValidationError(f"no version {config_version} for tenant {tenant_id}")
        digest = _version_hash(self._global, record.values)
        if digest != record.content_hash:
            raise ContentHashMismatchError(
                f"tenant {tenant_id} v{config_version}: stored {record.content_hash} != recomputed {digest}"
            )

    # ------------------------------------------------------------------ changes

    def _validate_patch(self, patch: dict[str, Any], category: str | None = None) -> None:
        try:
            assert_no_floats(patch)
        except FloatInConfigError as exc:
            raise ConfigValidationError(str(exc)) from exc
        _require_shape_consistent(self._global, patch)
        for path in flatten(patch):
            if path in NON_CONFIGURABLE_PATHS:
                raise NonConfigurableKeyError(
                    f"'{path}' is a closed, non-configurable enum and cannot be changed"
                )
            if path.split(".", 1)[0] not in self._global:
                raise ConfigValidationError(f"unknown config section for key '{path}'")

    async def propose_change(
        self,
        tenant_id: str,
        patch: dict[str, Any],
        *,
        base_config_version: int,
        category: str | None = None,
    ) -> str:
        """Validate, compute the candidate version, and create a ``pending_signature`` decision.

        Returns the decision id. Nothing is written to the version history here (ADR-400 §6).
        """
        self._validate_patch(patch, category)
        await self._require_baseline(tenant_id)
        current_version, current_patch = await self._tenant_patch(tenant_id)
        if base_config_version != current_version:
            raise StaleBaseVersionError(tenant_id, base_config_version, current_version)

        candidate_values = _apply_patch(current_patch, patch, category)
        candidate_tenant = {k: v for k, v in candidate_values.items() if k != CATEGORY_KEY}
        _validate_merged(deep_merge(self._global, candidate_tenant))
        _validate_all_categories(self._global, candidate_values)
        digest = _version_hash(self._global, candidate_values)
        candidate_version = current_version + 1

        decision = await self._decisions.create_decision(
            DECISION_TYPE_CONFIG_CHANGE,
            f"tenant:{tenant_id}:config",
            {
                "tenant_id": tenant_id,
                "base_config_version": current_version,
                "candidate_config_version": candidate_version,
                "candidate_content_hash": digest,
                "category": category,
                "patch": _copy_json(patch),
                "proposed_at": self._clock.now().isoformat(),
            },
        )
        return decision.id

    async def apply_signed_change(
        self,
        tenant_id: str,
        decision_id: str,
        patch: dict[str, Any],
        *,
        category: str | None = None,
    ) -> ConfigVersionRecord:
        """Append the new version, but only after ``require_signed`` succeeds.

        ``patch``/``category`` must be the exact ones the decision was created for; the candidate hash
        is re-derived and compared with the signed payload, so a tampered patch is rejected.
        """
        decision = await self._decisions.require_signed(decision_id)  # raises PendingSignature
        payload = decision.payload
        if payload.get("tenant_id") != tenant_id:
            raise ConfigValidationError("decision belongs to another tenant")
        if _copy_json(payload.get("patch")) != _copy_json(patch):
            raise ConfigValidationError("patch does not match the signed decision payload")

        await self._require_baseline(tenant_id)
        base = int(payload["base_config_version"])
        current_version, current_patch = await self._tenant_patch(tenant_id)
        if base != current_version:
            raise StaleBaseVersionError(tenant_id, base, current_version)

        if payload.get("category") != category:
            raise ConfigValidationError("category does not match the signed decision payload")
        candidate_values = _apply_patch(current_patch, patch, category)
        candidate_tenant = {k: v for k, v in candidate_values.items() if k != CATEGORY_KEY}
        _validate_merged(deep_merge(self._global, candidate_tenant))
        _validate_all_categories(self._global, candidate_values)
        digest = _version_hash(self._global, candidate_values)
        if digest != payload.get("candidate_content_hash"):
            raise ConfigValidationError("candidate content hash differs from the signed one")

        record = ConfigVersionRecord(
            tenant_id=tenant_id,
            config_version=current_version + 1,
            content_hash=digest,
            values=candidate_values,
            created_at=self._clock.now(),
            decision_id=decision_id,
        )
        await self._repo.append_version(record)
        return record


def _require_shape_consistent(
    base: dict[str, Any], patch: dict[str, Any], prefix: str = ""
) -> None:
    """Only leaves may be ``null``, and a patch may not turn a leaf into an object or the reverse.

    ADR-900: ``null`` means "unset" for a *leaf*. A whole section, ``llm.roles`` or ``seller.weights`` set to
    ``null`` is rejected. Keys whose global value is ``null`` are unset leaves (``sanity.floor_per_unit``,
    ``llm.roles``, ...): they may receive a value or ``null``. This also keeps deep-merge associative.
    """
    for key, value in patch.items():
        path = f"{prefix}.{key}" if prefix else key
        if key == CATEGORY_KEY:
            raise ConfigValidationError(f"'{path}' is reserved and cannot be patched directly")
        if key not in base:
            raise ConfigValidationError(f"unknown config key '{path}'")
        current = base[key]
        if isinstance(value, dict):
            if current is None:
                continue  # an unset leaf that holds a structured value (llm.roles, seller.weights)
            if not isinstance(current, dict):
                raise ConfigValidationError(f"'{path}' is a leaf, not an object")
            _require_shape_consistent(current, value, path)
        elif value is None and isinstance(current, dict):
            raise ConfigValidationError(f"'{path}' is a section: only leaves may be null")
        elif isinstance(current, dict):
            raise ConfigValidationError(f"'{path}' is a section, not a value")


def _apply_patch(
    current: dict[str, Any], patch: dict[str, Any], category: str | None
) -> dict[str, Any]:
    """Return the new accumulated tenant patch after applying ``patch`` (optionally per category)."""
    if category is None:
        return deep_merge(current, patch)
    cats = current.get(CATEGORY_KEY, {}) if isinstance(current.get(CATEGORY_KEY), dict) else {}
    updated_cat = deep_merge(cats.get(category, {}), patch)
    return deep_merge(current, {CATEGORY_KEY: {category: updated_cat}})


def _validate_merged(merged: dict[str, Any]) -> TenantConfig:
    """Validate a fully merged plain mapping against the typed model.

    A ``None`` for a required non-optional field is a validation error, which is the correct "unset is
    loud" behaviour for keys that must never be null in the typed model.
    """
    try:
        return TenantConfig.from_mapping(_model_shape(merged))
    except ValidationError as exc:
        raise ConfigValidationError(str(exc)) from exc


def _model_shape(merged: dict[str, Any]) -> dict[str, Any]:
    """Map the flat JSON sections onto ``TenantConfig`` field names.

    The defaults file uses the same section names as the model, so this is currently identity; the
    function is the single place to adapt if the JSON layout diverges from the model.
    """
    return merged


def _plain(merged: dict[str, Any]) -> dict[str, Any]:
    """The effective view without the ``categories`` block: what a request without a category sees."""
    return {k: v for k, v in merged.items() if k != CATEGORY_KEY}


def _version_hash(global_layer: dict[str, Any], tenant_values: dict[str, Any]) -> str:
    """Content hash that identifies a tenant config version, category overrides included (ADR-900).

    It covers the tenant's effective base view *and* the ``categories`` block, so any category patch
    changes the hash. ``effective(tenant, category)`` hashes what that category actually sees instead.
    """
    base = deep_merge(global_layer, {k: v for k, v in tenant_values.items() if k != CATEGORY_KEY})
    categories = tenant_values.get(CATEGORY_KEY, {})
    return content_hash({"base": _plain(base), "categories": categories if categories else {}})


def _validate_all_categories(global_layer: dict[str, Any], tenant_values: dict[str, Any]) -> None:
    """Every category override must produce a valid configuration when merged over the tenant view."""
    base = deep_merge(global_layer, {k: v for k, v in tenant_values.items() if k != CATEGORY_KEY})
    categories = tenant_values.get(CATEGORY_KEY, {})
    if not isinstance(categories, dict):
        raise ConfigValidationError("'categories' must be an object")
    for name, patch in categories.items():
        if not isinstance(patch, dict):
            raise ConfigValidationError(f"category '{name}' override must be an object")
        _require_shape_consistent(global_layer, patch, f"categories.{name}")
        try:
            _validate_merged(deep_merge(base, patch))
        except ConfigValidationError as exc:
            raise ConfigValidationError(f"category '{name}': {exc}") from exc


def _copy_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _copy_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy_json(v) for v in value]
    return value
