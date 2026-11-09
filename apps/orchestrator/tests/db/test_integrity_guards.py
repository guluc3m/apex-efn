"""Schema v1 integrity guards (D2-03): append-only triggers, guarded transitions and CHECK constraints."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from tests.db.conftest import postgres_available

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not postgres_available(), reason="no Postgres: set APEX_TEST_PG_ADMIN_URL or start Docker"
    ),
]

T0 = datetime(2026, 1, 1, tzinfo=UTC)
HASH = "a" * 64

APPEND_ONLY_TABLES = {
    "audit_events",
    "signatures",
    "fx_rates",
    "seller_signal_snapshots",
    "seller_confidences",
    "tenant_config_versions",
    "user_profile_preferences",
    "financial_rows",
}


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


@pytest.fixture
def conn(migrated_db: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(migrated_db, autocommit=True) as connection:
        yield connection


@dataclass
class Graph:
    """One row in every guarded table, all linked to a fresh tenant."""

    tenant: str
    user: str
    key: str
    session: str
    decision: str
    signature: str
    audit_event: str
    fx_rate: str
    seller: str
    signal_snapshot: str
    confidence: str
    profile: str
    financial_import: str
    financial_row: str
    snapshot: str
    snapshot_decision: str


def _insert(conn: psycopg.Connection, table: str, **values: object) -> str:
    columns = ", ".join(f'"{c}"' for c in values)
    placeholders = ", ".join(["%s"] * len(values))
    conn.execute(
        f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',  # type: ignore[arg-type]
        list(values.values()),
    )
    return str(values["id"])


def _tenant(conn: psycopg.Connection) -> str:
    return _insert(
        conn,
        "tenants",
        id=_id("tenant"),
        name="T",
        country="ES",
        base_currency="EUR",
        created_at=T0,
        updated_at=T0,
    )


def _decision(conn: psycopg.Connection, tenant: str, **overrides: object) -> str:
    values: dict[str, object] = {
        "id": _id("dec"),
        "tenant_id": tenant,
        "type": "follow",
        "subject_ref": "offer:o1",
        "payload_canonical": '{"a":1}',
        "payload_hash": HASH,
        "status": "pending_signature",
        "requires_immediate_reauth": False,
        "required_signers": 1,
        "created_by_type": "human",
        "created_by_id": "user-x",
        "created_at": T0,
    }
    values.update(overrides)
    return _insert(conn, "decisions", **values)


def _financial_import(conn: psycopg.Connection, tenant: str, status: str = "draft") -> str:
    return _insert(
        conn,
        "financial_imports",
        id=_id("imp"),
        tenant_id=tenant,
        status=status,
        csv_ref="s3://apex-csv/x.csv",
        csv_sha256=HASH,
        base_currency="EUR",
        report=Jsonb({"rows": []}),
        rows_ok=1,
        rows_rejected=0,
        projection_enabled=False,
        periods_loaded=1,
        created_by_type="human",
        created_by_id="user-x",
        created_at=T0,
    )


def _snapshot(
    conn: psycopg.Connection, tenant: str, import_id: str, decision: str, version: int = 1
) -> str:
    return _insert(
        conn,
        "financial_snapshots",
        id=_id("snap"),
        tenant_id=tenant,
        import_id=import_id,
        version=version,
        status="active",
        base_currency="EUR",
        decision_id=decision,
        activated_at=T0,
        activated_by_id="user-x",
        created_at=T0,
    )


@pytest.fixture
def graph(conn: psycopg.Connection) -> Graph:
    tenant = _tenant(conn)
    user = _insert(
        conn,
        "users",
        id=_id("user"),
        email=f"{uuid4().hex}@apex.local",
        display_name="U",
        created_at=T0,
        updated_at=T0,
    )
    key = _insert(
        conn,
        "signing_keys",
        id=_id("key"),
        owner_type="human",
        owner_id=user,
        user_id=user,
        tenant_id=tenant,
        public_key=uuid4().hex,
        alg="Ed25519",
        created_at=T0,
    )
    session = _insert(
        conn,
        "signing_sessions",
        id=_id("ss"),
        tenant_id=tenant,
        user_id=user,
        key_id=key,
        auth_method="keycloak_step_up",
        auth_at=T0,
        expires_at=T0 + timedelta(minutes=15),
        device_fingerprint_ref="dev-1",
        decisions_signed=[],
        max_decisions=10,
        status="active",
        created_at=T0,
    )
    decision = _decision(conn, tenant)
    signature = _insert(
        conn,
        "signatures",
        id=_id("sig"),
        tenant_id=tenant,
        decision_id=decision,
        signer_type="human",
        signer_id=user,
        key_id=key,
        alg="Ed25519",
        payload_hash=HASH,
        signature="c2ln",
        signed_at=T0,
        signing_session_id=session,
        auth_at=T0,
        chain_hash=uuid4().hex,
    )
    audit_event = _insert(
        conn,
        "audit_events",
        id=_id("ae"),
        tenant_id=tenant,
        seq=1,
        actor_type="human",
        actor_id=user,
        event_type="decision.created",
        subject_ref=f"decision:{decision}",
        payload=Jsonb({}),
        payload_hash=HASH,
        prev_hash="0" * 64,
        hash=uuid4().hex,
        created_at=T0,
    )
    fx_rate = _insert(
        conn,
        "fx_rates",
        id=_id("fx"),
        base="EUR",
        quote="USD",
        rate="1.0850",
        as_of=T0 + timedelta(seconds=uuid4().int % 10_000_000),
        source="ecb",
        ingested_at=T0,
    )
    seller = _insert(
        conn,
        "sellers",
        id=_id("seller"),
        canonical_id=uuid4().hex,
        name="S",
        risk_flags=[],
        created_at=T0,
        updated_at=T0,
    )
    signal_snapshot = _insert(
        conn,
        "seller_signal_snapshots",
        id=_id("sss"),
        seller_id=seller,
        platform="mock-a",
        signal_count=3,
        data_completeness="0.5",
        raw=Jsonb({}),
        captured_at=T0,
    )
    _insert(
        conn,
        "tenant_config_versions",
        id=_id("cfg"),
        tenant_id=tenant,
        config_version=1,
        content_hash=HASH,
        values=Jsonb({}),
        created_by_type="service",
        created_by_id="load_defaults",
        created_at=T0,
    )
    confidence = _insert(
        conn,
        "seller_confidences",
        id=_id("sc"),
        tenant_id=tenant,
        seller_id=seller,
        snapshot_id=signal_snapshot,
        score=72,
        band="medium",
        signals_normalized=Jsonb({}),
        penalties=[],
        flags=Jsonb([]),
        model_version="trust-v1",
        config_version=1,
        computed_at=T0,
    )
    profile = _insert(
        conn,
        "user_profile_preferences",
        id=_id("pref"),
        tenant_id=tenant,
        profile_key="balanced",
        version=1,
        name="Balanced",
        weights=Jsonb({}),
        negotiation=Jsonb({}),
        hard_constraints=Jsonb({}),
        created_by_type="human",
        created_by_id=user,
        created_at=T0,
    )
    financial_import = _financial_import(conn, tenant)
    financial_row = _insert(
        conn,
        "financial_rows",
        id=_id("row"),
        tenant_id=tenant,
        import_id=financial_import,
        row_number=1,
        period="2026-10",
        metric="cash_balance",
        value_minor=1_000_000,
        currency="EUR",
        converted=False,
    )
    activated_import = _financial_import(conn, tenant, status="active")
    snapshot_decision = _decision(
        conn,
        tenant,
        type="activate_financial_snapshot",
        status="signed",
        signed_at=T0,
        requires_immediate_reauth=True,
    )
    snapshot = _snapshot(conn, tenant, activated_import, snapshot_decision)
    return Graph(
        tenant=tenant,
        user=user,
        key=key,
        session=session,
        decision=decision,
        signature=signature,
        audit_event=audit_event,
        fx_rate=fx_rate,
        seller=seller,
        signal_snapshot=signal_snapshot,
        confidence=confidence,
        profile=profile,
        financial_import=financial_import,
        financial_row=financial_row,
        snapshot=snapshot,
        snapshot_decision=snapshot_decision,
    )


def _guard(conn: psycopg.Connection, sql: str, params: list[object] | None = None) -> str:
    with pytest.raises(psycopg.errors.IntegrityConstraintViolation) as excinfo:
        conn.execute(sql, params)  # type: ignore[arg-type]
    return str(excinfo.value)


def _check(conn: psycopg.Connection, sql: str, params: list[object] | None = None) -> str:
    with pytest.raises(psycopg.errors.CheckViolation) as excinfo:
        conn.execute(sql, params)  # type: ignore[arg-type]
    return str(excinfo.value)


# --- schema shape ----------------------------------------------------------------------------------------------


def test_pgvector_and_langgraph_schema_exist(conn: psycopg.Connection) -> None:
    assert conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()
    assert conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'langgraph'").fetchone()
    column = conn.execute(
        "SELECT udt_name FROM information_schema.columns "
        "WHERE table_name = 'product_embeddings' AND column_name = 'embedding'"
    ).fetchone()
    assert column == ("vector",)


def test_money_columns_are_bigint_and_fx_rates_are_numeric(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND (column_name LIKE '%%\\_minor' OR column_name = 'fx_rate' "
        "OR (table_name = 'fx_rates' AND column_name = 'rate'))"
    ).fetchall()
    assert rows
    for table, column, data_type in rows:
        expected = "numeric" if column in {"fx_rate", "rate"} else "bigint"
        assert data_type == expected, f"{table}.{column} is {data_type}"


def test_currency_columns_use_the_closed_enum(conn: psycopg.Connection) -> None:
    labels = conn.execute(
        "SELECT array_agg(enumlabel::text ORDER BY enumsortorder) FROM pg_enum e "
        "JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = 'Currency'"
    ).fetchone()
    assert labels == (["EUR", "USD", "CNY"],)
    loose = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public' "
        "AND (column_name = 'currency' OR column_name LIKE '%%\\_currency') AND udt_name <> 'Currency'"
    ).fetchall()
    assert loose == []


def test_append_only_triggers_cover_exactly_the_expected_tables(conn: psycopg.Connection) -> None:
    rows = conn.execute(
        "SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_proc p ON p.oid = t.tgfoid "
        "WHERE p.proname = 'apex_forbid_mutation' AND t.tgname LIKE '%%\\_append_only'"
    ).fetchall()
    assert {r[0] for r in rows} == APPEND_ONLY_TABLES


# --- append-only tables ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "attr", "column", "value"),
    [
        ("audit_events", "audit_event", "event_type", "tampered"),
        ("signatures", "signature", "signature", "Zm9yZ2Vk"),
        ("fx_rates", "fx_rate", "rate", "2"),
        ("seller_signal_snapshots", "signal_snapshot", "signal_count", 99),
        ("seller_confidences", "confidence", "score", 99),
        ("user_profile_preferences", "profile", "name", "tampered"),
        ("financial_rows", "financial_row", "value_minor", 1),
    ],
)
def test_append_only_rows_cannot_be_updated_or_deleted(
    conn: psycopg.Connection, graph: Graph, table: str, attr: str, column: str, value: object
) -> None:
    row_id = getattr(graph, attr)
    message = _guard(conn, f'UPDATE "{table}" SET "{column}" = %s WHERE id = %s', [value, row_id])
    assert "append-only" in message
    _guard(conn, f'DELETE FROM "{table}" WHERE id = %s', [row_id])
    assert conn.execute(f'SELECT count(*) FROM "{table}" WHERE id = %s', [row_id]).fetchone() == (
        1,
    )  # type: ignore[arg-type]


def test_tenant_config_versions_are_append_only(conn: psycopg.Connection, graph: Graph) -> None:
    _guard(
        conn,
        "UPDATE tenant_config_versions SET content_hash = %s WHERE tenant_id = %s",
        ["b" * 64, graph.tenant],
    )
    _guard(conn, "DELETE FROM tenant_config_versions WHERE tenant_id = %s", [graph.tenant])


@pytest.mark.parametrize("table", sorted(APPEND_ONLY_TABLES | {"financial_snapshots", "decisions"}))
def test_guarded_tables_cannot_be_truncated(
    conn: psycopg.Connection, graph: Graph, table: str
) -> None:
    _guard(conn, f'TRUNCATE "{table}" CASCADE')


# --- financial snapshots ---------------------------------------------------------------------------------------


def test_snapshot_can_only_move_from_active_to_superseded(
    conn: psycopg.Connection, graph: Graph
) -> None:
    _guard(conn, "UPDATE financial_snapshots SET version = 7 WHERE id = %s", [graph.snapshot])
    _guard(
        conn, "UPDATE financial_snapshots SET status = 'superseded' WHERE id = %s", [graph.snapshot]
    )
    _guard(
        conn,
        "UPDATE financial_snapshots SET status = 'superseded', superseded_at = %s, activated_by_id = 'x' WHERE id = %s",
        [T0, graph.snapshot],
    )
    _guard(conn, "DELETE FROM financial_snapshots WHERE id = %s", [graph.snapshot])

    conn.execute(
        "UPDATE financial_snapshots SET status = 'superseded', superseded_at = %s WHERE id = %s",
        [T0, graph.snapshot],
    )

    _guard(
        conn,
        "UPDATE financial_snapshots SET status = 'active', superseded_at = NULL WHERE id = %s",
        [graph.snapshot],
    )
    _guard(
        conn,
        "UPDATE financial_snapshots SET superseded_at = %s WHERE id = %s",
        [T0 + timedelta(1), graph.snapshot],
    )


def test_only_one_active_snapshot_per_tenant(conn: psycopg.Connection, graph: Graph) -> None:
    second_import = _financial_import(conn, graph.tenant, status="active")
    decision = _decision(
        conn, graph.tenant, type="activate_financial_snapshot", status="signed", signed_at=T0
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        _snapshot(conn, graph.tenant, second_import, decision, version=2)

    conn.execute(
        "UPDATE financial_snapshots SET status = 'superseded', superseded_at = %s WHERE id = %s",
        [T0, graph.snapshot],
    )
    _snapshot(conn, graph.tenant, second_import, decision, version=2)


# --- financial imports -----------------------------------------------------------------------------------------


def test_financial_import_transitions(conn: psycopg.Connection, graph: Graph) -> None:
    _guard(conn, "UPDATE financial_imports SET rows_ok = 5 WHERE id = %s", [graph.financial_import])
    _guard(
        conn,
        "UPDATE financial_imports SET status = 'superseded' WHERE id = %s",
        [graph.financial_import],
    )
    conn.execute(
        "UPDATE financial_imports SET status = 'active' WHERE id = %s", [graph.financial_import]
    )
    _guard(
        conn,
        "UPDATE financial_imports SET status = 'draft' WHERE id = %s",
        [graph.financial_import],
    )
    _guard(conn, "DELETE FROM financial_imports WHERE id = %s", [graph.financial_import])
    conn.execute(
        "UPDATE financial_imports SET status = 'superseded' WHERE id = %s", [graph.financial_import]
    )


def test_draft_import_can_be_deleted(conn: psycopg.Connection, graph: Graph) -> None:
    draft = _financial_import(conn, graph.tenant)
    conn.execute("DELETE FROM financial_imports WHERE id = %s", [draft])
    assert conn.execute(
        "SELECT count(*) FROM financial_imports WHERE id = %s", [draft]
    ).fetchone() == (0,)


# --- decisions -------------------------------------------------------------------------------------------------


def test_decision_payload_is_immutable(conn: psycopg.Connection, graph: Graph) -> None:
    message = _guard(
        conn, "UPDATE decisions SET payload_canonical = '{\"a\":2}' WHERE id = %s", [graph.decision]
    )
    assert "immutable" in message
    _guard(conn, "UPDATE decisions SET required_signers = 2 WHERE id = %s", [graph.decision])
    _guard(conn, "DELETE FROM decisions WHERE id = %s", [graph.decision])


def test_decision_is_frozen_once_signed(conn: psycopg.Connection, graph: Graph) -> None:
    conn.execute(
        "UPDATE decisions SET status = 'signed', signed_at = %s WHERE id = %s", [T0, graph.decision]
    )
    _guard(
        conn,
        "UPDATE decisions SET status = 'rejected', signed_at = NULL, rejected_at = %s WHERE id = %s",
        [T0, graph.decision],
    )


def test_decision_status_and_timestamps_agree(conn: psycopg.Connection, graph: Graph) -> None:
    _check(conn, "UPDATE decisions SET status = 'signed' WHERE id = %s", [graph.decision])
    with pytest.raises(psycopg.errors.CheckViolation):
        _decision(conn, graph.tenant, required_signers=3)


# --- CHECK constraints -----------------------------------------------------------------------------------------


def test_human_signature_requires_a_signing_session(conn: psycopg.Connection, graph: Graph) -> None:
    decision = _decision(conn, graph.tenant)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(
            conn,
            "signatures",
            id=_id("sig"),
            tenant_id=graph.tenant,
            decision_id=decision,
            signer_type="human",
            signer_id=graph.user,
            key_id=graph.key,
            alg="Ed25519",
            payload_hash=HASH,
            signature="c2ln",
            signed_at=T0,
            chain_hash=uuid4().hex,
        )


def test_service_key_can_sign_without_a_session(conn: psycopg.Connection, graph: Graph) -> None:
    service_key = _insert(
        conn,
        "signing_keys",
        id=_id("key"),
        owner_type="service",
        owner_id="gate-agent",
        public_key=uuid4().hex,
        alg="Ed25519",
        vault_key_ref="transit/keys/gate-agent",
        created_at=T0,
    )
    decision = _decision(conn, graph.tenant, created_by_type="service", created_by_id="gate-agent")
    _insert(
        conn,
        "signatures",
        id=_id("sig"),
        tenant_id=graph.tenant,
        decision_id=decision,
        signer_type="service",
        signer_id="gate-agent",
        key_id=service_key,
        alg="Ed25519",
        payload_hash=HASH,
        signature="c2ln",
        signed_at=T0,
        chain_hash=uuid4().hex,
    )


def test_human_key_must_belong_to_its_user(conn: psycopg.Connection, graph: Graph) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(
            conn,
            "signing_keys",
            id=_id("key"),
            owner_type="human",
            owner_id="someone-else",
            user_id=graph.user,
            tenant_id=graph.tenant,
            public_key=uuid4().hex,
            alg="Ed25519",
            created_at=T0,
        )


def test_signing_session_window_must_be_positive(conn: psycopg.Connection, graph: Graph) -> None:
    _check(
        conn,
        "UPDATE signing_sessions SET expires_at = auth_at WHERE id = %s",
        [graph.session],
    )


def test_financial_row_rules(conn: psycopg.Connection, graph: Graph) -> None:
    base: dict[str, object] = {
        "tenant_id": graph.tenant,
        "import_id": graph.financial_import,
        "metric": "cash_balance",
        "converted": False,
    }
    bad_rows: list[dict[str, object]] = [
        {"period": "2026-13", "value_minor": 1, "currency": "EUR"},
        {"period": "2026-10", "value_minor": 1, "value_bp": 1, "currency": "EUR"},
        {"period": "2026-10", "value_minor": 1},
        {"period": "2026-10", "metric": "budget", "value_minor": 1, "currency": "EUR"},
    ]
    for number, overrides in enumerate(bad_rows, start=100):
        with pytest.raises(psycopg.errors.CheckViolation):
            _insert(
                conn, "financial_rows", id=_id("row"), row_number=number, **{**base, **overrides}
            )


def test_seller_confidence_score_only_null_for_insufficient_data(
    conn: psycopg.Connection, graph: Graph
) -> None:
    common: dict[str, object] = {
        "tenant_id": graph.tenant,
        "seller_id": graph.seller,
        "signals_normalized": Jsonb({}),
        "penalties": [],
        "flags": Jsonb([]),
        "model_version": "trust-v1",
        "config_version": 1,
        "computed_at": T0,
    }
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, "seller_confidences", id=_id("sc"), score=None, band="medium", **common)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(
            conn, "seller_confidences", id=_id("sc"), score=10, band="insufficient_data", **common
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(conn, "seller_confidences", id=_id("sc"), score=101, band="high", **common)
    _insert(
        conn, "seller_confidences", id=_id("sc"), score=None, band="insufficient_data", **common
    )


def test_seller_confidence_requires_an_existing_config_version(
    conn: psycopg.Connection, graph: Graph
) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _insert(
            conn,
            "seller_confidences",
            id=_id("sc"),
            tenant_id=graph.tenant,
            seller_id=graph.seller,
            score=50,
            band="medium",
            signals_normalized=Jsonb({}),
            penalties=[],
            flags=Jsonb([]),
            model_version="trust-v1",
            config_version=42,
            computed_at=T0,
        )
