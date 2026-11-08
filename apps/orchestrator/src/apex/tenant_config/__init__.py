"""Tenant configuration service owned by DEV-4 (ADR-400, spec §7).

This package is built in stacked steps. This module exports only the pure domain (models, errors,
resolver, ports, repository); the service and the API arrive in later stacked branches.
"""

from apex.tenant_config.errors import (
    ConfigKeyUnset,
    ConfigValidationError,
    NonConfigurableKeyError,
    StaleBaseVersionError,
    TenantConfigError,
)
from apex.tenant_config.models import SUPPORTED_CURRENCIES, Band, TenantConfig
from apex.tenant_config.resolver import EffectiveConfig, Layer, ResolvedValue

__all__ = [
    "SUPPORTED_CURRENCIES",
    "Band",
    "ConfigKeyUnset",
    "ConfigValidationError",
    "EffectiveConfig",
    "Layer",
    "NonConfigurableKeyError",
    "ResolvedValue",
    "StaleBaseVersionError",
    "TenantConfig",
    "TenantConfigError",
]
