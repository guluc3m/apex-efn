"""D2-10 wiring (issue #352): the app exposes the anchor store and the worker gets the real audit job."""

from __future__ import annotations

from apex.audit.anchor import Boto3AnchorStore
from apex.audit.service import AuditChainService
from apex.config import Settings
from apex.main import create_app
from apex.wiring import build_worker_ports


def test_app_state_has_the_anchor_store_on_the_audit_bucket() -> None:
    app = create_app(Settings())
    store = app.state.anchor_store
    assert isinstance(store, Boto3AnchorStore) and store.bucket == Settings().s3_bucket_audit


def test_worker_ports_wire_only_the_audit_job() -> None:
    ports = build_worker_ports(Settings())
    assert isinstance(ports.audit, AuditChainService)
    assert type(ports.gate).__name__.startswith("Unwired")
