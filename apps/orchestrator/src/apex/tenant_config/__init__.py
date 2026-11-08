"""Tenant configuration service (ADR-400, spec §7).

Public surface: ``effective``, ``propose_change``, ``apply_signed_change`` via ``TenantConfigService``.
"""

from apex.tenant_config.errors import (
    ConfigKeyUnset,
    ConfigValidationError,
    NonConfigurableKeyError,
    StaleBaseVersionError,
    TenantConfigError,
)
from apex.tenant_config.models import SUPPORTED_CURRENCIES, Band, TenantConfig
from apex.tenant_config.repository import InMemoryConfigRepository
from apex.tenant_config.resolver import EffectiveConfig, Layer, ResolvedValue
from apex.tenant_config.service import TenantConfigService

__all__ = [
    "SUPPORTED_CURRENCIES",
    "Band",
    "ConfigKeyUnset",
    "ConfigValidationError",
    "EffectiveConfig",
    "InMemoryConfigRepository",
    "Layer",
    "NonConfigurableKeyError",
    "ResolvedValue",
    "StaleBaseVersionError",
    "TenantConfig",
    "TenantConfigError",
    "TenantConfigService",
]
