"""Typed model accepts the shipped defaults and rejects invalid seller weights."""

from __future__ import annotations

import pytest

from apex.tenant_config.models import TenantConfig


def test_typed_model_accepts_the_shipped_defaults() -> None:
    from apex.tenant_config.defaults import load_global_layer

    _, values = load_global_layer()
    TenantConfig.from_mapping(values)


def test_seller_weights_must_sum_to_one_when_set() -> None:
    from pydantic import ValidationError

    from apex.tenant_config.defaults import load_global_layer

    _, values = load_global_layer()
    values["seller"]["weights"] = {"a": 0.5, "b": 0.6}
    with pytest.raises(ValidationError):
        TenantConfig.from_mapping(values)
