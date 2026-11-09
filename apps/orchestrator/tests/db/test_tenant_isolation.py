"""Tenant isolation through row-level security (D2-04, criterion 30).

The test discovers every table in ``public`` from the catalog, so a table added by a later migration is covered
without editing this file. For each table it builds one valid row for tenant A, writing through a login role
in ``apex_app`` (the application role) with ``app.tenant_id`` set to A. Parent rows are created the same way,
following the foreign keys. Then, as tenant B and with no tenant at all, it checks that nothing of A can be
read, updated, deleted or written.

The row factory fills NOT NULL columns from their type, leaves nullable columns empty and uses the overrides
below only where a CHECK constraint needs a specific value. A new table with a new CHECK may need an override.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from tests.db.conftest import postgres_available

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not postgres_available(), reason="no Postgres: set APEX_TEST_PG_ADMIN_URL or start Docker"
    ),
]

T0 = datetime(2026, 1, 1, tzinfo=UTC)
TENANT_A = "tenant-iso-a"
TENANT_B = "tenant-iso-b"

# Tables without tenant_id and without RLS: global reference data (ADR-205, ADR-206).
GLOBAL_TABLES = {
    "sellers",
    "seller_platform_ids",
    "seller_signal_snapshots",
    "fx_rates",
    "_prisma_migrations",
}
# Tables without tenant_id that still have RLS with their own policies.
SPECIAL_RLS_TABLES = {"tenants", "users"}

OVERRIDES: dict[str, dict[str, object]] = {
    "signing_keys": {"owner_type": "service", "owner_id": "svc-isolation-test"},
    "signatures": {"signer_type": "service"},
    "signing_sessions": {"auth_at": T0, "expires_at": T0 + timedelta(minutes=15)},
    "financial_rows": {
        "period": "2026-10",
        "metric": "cash_balance",
        "value_minor": 1,
        "currency": "EUR",
    },
    "seller_confidences": {"score": 50, "band": "medium"},
    "negotiation_outcomes": {"outcome": "no_agreement"},
    "fx_rates": {"base": "EUR", "quote": "USD"},
}


@dataclass
class Catalog:
    columns: dict[str, list[dict[str, Any]]]
    foreign_keys: dict[str, list[tuple[list[str], str, list[str]]]]
    enums: dict[str, list[str]]
    tables: list[str] = field(default_factory=list)

    def has_tenant_id(self, table: str) -> bool:
        return any(c["name"] == "tenant_id" for c in self.columns[table])

    def nullable(self, table: str, column: str) -> bool:
        return next(c["nullable"] for c in self.columns[table] if c["name"] == column)


def _load_catalog(conn: psycopg.Connection) -> Catalog:
    columns: dict[str, list[dict[str, Any]]] = {}
    for table, name, data_type, udt, nullable, length in conn.execute(
        "SELECT c.table_name, c.column_name, c.data_type, c.udt_name, c.is_nullable = 'YES', "
        "c.character_maximum_length FROM information_schema.columns c "
        "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
        "WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE' ORDER BY c.table_name, c.ordinal_position"
    ):
        columns.setdefault(table, []).append(
            {"name": name, "type": data_type, "udt": udt, "nullable": nullable, "length": length}
        )
    foreign_keys: dict[str, list[tuple[list[str], str, list[str]]]] = {}
    for child, parent, cols, refcols in conn.execute(
        "SELECT cl.relname, pcl.relname, "
        "  array(SELECT a.attname::text FROM unnest(con.conkey) WITH ORDINALITY k(n, i) "
        "        JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.n ORDER BY k.i), "
        "  array(SELECT a.attname::text FROM unnest(con.confkey) WITH ORDINALITY k(n, i) "
        "        JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.n ORDER BY k.i) "
        "FROM pg_constraint con JOIN pg_class cl ON cl.oid = con.conrelid JOIN pg_class pcl ON pcl.oid = con.confrelid "
        "WHERE con.contype = 'f' AND con.connamespace = 'public'::regnamespace ORDER BY cl.relname, con.conname"
    ):
        foreign_keys.setdefault(child, []).append((list(cols), parent, list(refcols)))
    enums: dict[str, list[str]] = {}
    for name, labels in conn.execute(
        "SELECT t.typname, array_agg(e.enumlabel::text ORDER BY e.enumsortorder) "
        "FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid GROUP BY t.typname"
    ):
        enums[name] = list(labels)
    return Catalog(columns=columns, foreign_keys=foreign_keys, enums=enums, tables=sorted(columns))


class RowFactory:
    """Creates one valid row per table, following NOT NULL foreign keys, inside the current tenant context."""

    def __init__(self, conn: psycopg.Connection, catalog: Catalog, tenant: str) -> None:
        self.conn = conn
        self.catalog = catalog
        self.tenant = tenant
        self.rows: dict[str, dict[str, object]] = {}
        self._building: set[str] = set()

    def ensure(self, table: str) -> dict[str, object]:
        if table in self.rows:
            return self.rows[table]
        if table in self._building:
            raise AssertionError(f"NOT NULL foreign key cycle through {table}")
        self._building.add(table)
        try:
            values = self._values(table)
            self.insert(table, values)
        finally:
            self._building.discard(table)
        self.rows[table] = values
        return values

    def insert(self, table: str, values: dict[str, object]) -> None:
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(c) for c in values),
            sql.SQL(", ").join(sql.Placeholder() * len(values)),
        )
        self.conn.execute(query, [_adapt(v) for v in values.values()])

    def _values(self, table: str) -> dict[str, object]:
        values: dict[str, object] = {}
        overrides = OVERRIDES.get(table, {})
        for cols, parent, refcols in self.catalog.foreign_keys.get(table, []):
            own = [c for c in cols if c != "tenant_id"]
            if "tenant_id" in cols:
                self.ensure("tenants")
            if not own or any(c in overrides for c in own):
                continue
            if any(self.catalog.nullable(table, c) for c in own):
                continue
            parent_row = self.ensure(parent)
            for col, ref in zip(cols, refcols, strict=True):
                if col != "tenant_id":
                    values[col] = parent_row[ref]
        for column in self.catalog.columns[table]:
            name = column["name"]
            if name in values:
                continue
            if name in overrides:
                values[name] = overrides[name]
            elif name == "tenant_id" or (table == "tenants" and name == "id"):
                values[name] = self.tenant
            elif column["nullable"]:
                values[name] = None
            else:
                values[name] = self._value(table, column)
        return values

    def _value(self, table: str, column: dict[str, Any]) -> object:
        name, data_type, udt = column["name"], column["type"], column["udt"]
        if name.endswith("hash") or name.endswith("sha256"):
            return hashlib.sha256(uuid4().bytes).hexdigest()
        if name == "alg":
            return "Ed25519"
        if data_type == "ARRAY":
            element = udt.removeprefix("_")
            return [self.catalog.enums[element][0]] if element in self.catalog.enums else []
        if data_type == "USER-DEFINED":
            if udt == "vector":
                return "[1,2,3]"
            return self.catalog.enums[udt][0]
        if data_type in {"text", "character varying"}:
            if name == "email":
                return f"{uuid4().hex}@isolation.test"
            return f"{table}-{name}-{uuid4().hex[:12]}"
        if data_type == "character":
            return "ES" if column["length"] == 2 else "x" * column["length"]
        if data_type in {"integer", "bigint"}:
            return 1
        if data_type == "numeric":
            return "0.5"
        if data_type == "boolean":
            return False
        if data_type == "timestamp with time zone":
            return T0
        if data_type == "date":
            return date(2026, 1, 1)
        if data_type == "jsonb":
            return {}
        raise AssertionError(f"no value rule for {table}.{name} ({data_type}/{udt})")


def _adapt(value: object) -> object:
    return Jsonb(value) if isinstance(value, dict) else value


def _set_tenant(conn: psycopg.Connection, tenant: str | None) -> None:
    conn.execute("SELECT set_config('app.tenant_id', %s, false)", [tenant or ""])


@dataclass
class World:
    catalog: Catalog
    rows_a: dict[str, dict[str, object]]
    app_url: str


@pytest.fixture(scope="module")
def world(migrated_db: str, app_db: str) -> World:
    with psycopg.connect(migrated_db) as admin:
        catalog = _load_catalog(admin)
    with psycopg.connect(app_db, autocommit=True) as conn:
        _set_tenant(conn, TENANT_B)
        RowFactory(conn, catalog, TENANT_B).ensure("tenants")
        _set_tenant(conn, TENANT_A)
        factory = RowFactory(conn, catalog, TENANT_A)
        for table in catalog.tables:
            if table != "_prisma_migrations":
                factory.ensure(table)
        # The users policy shows a user to the tenants it belongs to, so give the generated user a membership.
        user_id = factory.rows["users"]["id"]
        membership = factory.rows["memberships"]
        if membership["user_id"] != user_id:
            factory.insert(
                "memberships", {**membership, "id": f"m-{uuid4().hex}", "user_id": user_id}
            )
    return World(catalog=catalog, rows_a=factory.rows, app_url=app_db)


@pytest.fixture
def app(world: World) -> Iterator[psycopg.Connection]:
    with psycopg.connect(world.app_url, autocommit=True) as conn:
        yield conn


def _isolated_tables(world: World) -> list[str]:
    return [t for t in world.catalog.tables if t not in GLOBAL_TABLES]


def _key(world: World, table: str) -> tuple[str, object]:
    column = "id" if any(c["name"] == "id" for c in world.catalog.columns[table]) else "tenant_id"
    return column, world.rows_a[table][column]


def _count(conn: psycopg.Connection, world: World, table: str) -> int:
    column, value = _key(world, table)
    query = sql.SQL("SELECT count(*) FROM {} WHERE {} = %s").format(
        sql.Identifier(table), sql.Identifier(column)
    )
    row = conn.execute(query, [value]).fetchone()
    assert row is not None
    return int(row[0])


def _touch(conn: psycopg.Connection, world: World, table: str, statement: str) -> int:
    column, value = _key(world, table)
    if statement == "UPDATE":
        query = sql.SQL("UPDATE {t} SET {c} = {c} WHERE {c} = %s").format(
            t=sql.Identifier(table), c=sql.Identifier(column)
        )
    else:
        query = sql.SQL("DELETE FROM {t} WHERE {c} = %s").format(
            t=sql.Identifier(table), c=sql.Identifier(column)
        )
    return conn.execute(query, [value]).rowcount


# --- the catalog is fully covered ------------------------------------------------------------------------------


def test_every_table_is_tenant_scoped_or_explicitly_global(world: World) -> None:
    unclassified = [
        t
        for t in world.catalog.tables
        if not world.catalog.has_tenant_id(t) and t not in GLOBAL_TABLES | SPECIAL_RLS_TABLES
    ]
    assert unclassified == [], (
        "add tenant_id and RLS, or list the table as global in ADR-206 and this test"
    )


def test_every_isolated_table_has_forced_rls_and_a_policy(migrated_db: str, world: World) -> None:
    with psycopg.connect(migrated_db) as admin:
        state = {
            name: (enabled, forced, policies)
            for name, enabled, forced, policies in admin.execute(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                "(SELECT count(*) FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = c.relname) "
                "FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'"
            )
        }
    missing = [
        t for t in _isolated_tables(world) if not (state[t][0] and state[t][1] and state[t][2] >= 1)
    ]
    assert missing == []


def test_app_role_is_not_privileged(migrated_db: str) -> None:
    with psycopg.connect(migrated_db) as admin:
        role = admin.execute(
            "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles WHERE rolname = 'apex_app'"
        ).fetchone()
        owned = admin.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner "
            "WHERE r.rolname = 'apex_app' AND c.relnamespace IN ('public'::regnamespace, 'langgraph'::regnamespace)"
        ).fetchone()
        langgraph = admin.execute(
            "SELECT has_schema_privilege('apex_app', 'langgraph', 'USAGE')"
        ).fetchone()
    assert role == (False, False, False, False)
    assert owned == (0,)
    assert langgraph == (True,)


def test_app_role_cannot_change_the_schema(app: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app.execute("ALTER TABLE offers DISABLE ROW LEVEL SECURITY")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app.execute("DROP POLICY tenant_isolation ON offers")


# --- tenant A sees its own rows --------------------------------------------------------------------------------


def test_owner_tenant_sees_its_rows(app: psycopg.Connection, world: World) -> None:
    _set_tenant(app, TENANT_A)
    invisible = [t for t in _isolated_tables(world) if _count(app, world, t) != 1]
    assert invisible == []


# --- tenant B sees and changes nothing -------------------------------------------------------------------------


def test_other_tenant_reads_nothing(app: psycopg.Connection, world: World) -> None:
    _set_tenant(app, TENANT_B)
    leaked = [t for t in _isolated_tables(world) if _count(app, world, t) != 0]
    assert leaked == []
    totals = {
        t: app.execute(
            sql.SQL("SELECT count(*) FROM {} WHERE tenant_id IS NOT NULL").format(sql.Identifier(t))
        ).fetchone()
        for t in _isolated_tables(world)
        if t not in SPECIAL_RLS_TABLES
    }
    assert {t: n for t, n in totals.items() if n != (0,)} == {}


@pytest.mark.parametrize("statement", ["UPDATE", "DELETE"])
def test_other_tenant_changes_nothing(
    app: psycopg.Connection, world: World, statement: str
) -> None:
    _set_tenant(app, TENANT_B)
    touched = [t for t in _isolated_tables(world) if _touch(app, world, t, statement) != 0]
    assert touched == []
    _set_tenant(app, TENANT_A)
    assert [t for t in _isolated_tables(world) if _count(app, world, t) != 1] == []


def test_other_tenant_cannot_write_rows_for_tenant_a(app: psycopg.Connection, world: World) -> None:
    _set_tenant(app, TENANT_B)
    accepted: list[str] = []
    for table in _isolated_tables(world):
        if table == "users":
            continue  # global rows: covered by test_users_are_visible_only_to_member_tenants
        values = {**world.rows_a[table]}
        if "id" in values:
            values["id"] = f"{table}-forged-{uuid4().hex[:12]}" if table != "tenants" else TENANT_A
        try:
            RowFactory(app, world.catalog, TENANT_B).insert(table, values)
        except psycopg.errors.InsufficientPrivilege as error:
            assert "row-level security" in str(error)
        else:
            accepted.append(table)
    assert accepted == []


def test_users_are_visible_only_to_member_tenants(app: psycopg.Connection, world: World) -> None:
    user_id = world.rows_a["users"]["id"]
    _set_tenant(app, TENANT_A)
    assert app.execute("SELECT count(*) FROM users WHERE id = %s", [user_id]).fetchone() == (1,)
    _set_tenant(app, TENANT_B)
    assert app.execute("SELECT count(*) FROM users WHERE id = %s", [user_id]).fetchone() == (0,)


# --- no tenant context fails closed ----------------------------------------------------------------------------


def test_no_tenant_context_sees_nothing(app: psycopg.Connection, world: World) -> None:
    for tenant in (None, ""):
        _set_tenant(app, tenant)
        leaked = [t for t in _isolated_tables(world) if _count(app, world, t) != 0]
        assert leaked == []


def test_no_tenant_context_cannot_write_tenant_rows(app: psycopg.Connection, world: World) -> None:
    _set_tenant(app, None)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        RowFactory(app, world.catalog, TENANT_A).insert(
            "offers", {**world.rows_a["offers"], "id": f"offer-forged-{uuid4().hex[:12]}"}
        )


def test_transaction_local_tenant_does_not_leak_to_the_next_transaction(world: World) -> None:
    with psycopg.connect(world.app_url) as conn:
        with conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", [TENANT_A])
            assert _count(conn, world, "offers") == 1
        assert _count(conn, world, "offers") == 0


# --- global keys and LLM events --------------------------------------------------------------------------------


def test_global_service_keys_are_readable_but_only_writable_without_a_tenant(
    app: psycopg.Connection, world: World
) -> None:
    key = {
        "id": f"key-global-{uuid4().hex[:12]}",
        "owner_type": "service",
        "owner_id": "gate-agent",
        "tenant_id": None,
        "public_key": uuid4().hex,
        "alg": "Ed25519",
        "vault_key_ref": "transit/keys/gate-agent",
        "created_at": T0,
    }
    factory = RowFactory(app, world.catalog, TENANT_A)
    _set_tenant(app, TENANT_A)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        factory.insert("signing_keys", key)
    _set_tenant(app, None)
    factory.insert("signing_keys", key)
    _set_tenant(app, TENANT_B)
    assert app.execute(
        "SELECT count(*) FROM signing_keys WHERE id = %s", [key["id"]]
    ).fetchone() == (1,)
    assert (
        app.execute(
            "UPDATE signing_keys SET revoked_at = %s WHERE id = %s", [T0, key["id"]]
        ).rowcount
        == 0
    )
    assert app.execute("DELETE FROM signing_keys WHERE id = %s", [key["id"]]).rowcount == 0
    _set_tenant(app, None)
    assert app.execute(
        "SELECT count(*) FROM signing_keys WHERE id = %s", [key["id"]]
    ).fetchone() == (1,)
