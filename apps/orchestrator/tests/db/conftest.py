"""A fresh Postgres database with every Prisma migration applied (D2-03, D2-04).

Two ways to get a server, in this order:
1. ``APEX_TEST_PG_ADMIN_URL``: a superuser URL of a running Postgres 16 with pgvector. A throwaway database is
   created on it for the test module and dropped afterwards. Useful without Docker.
2. Testcontainers with the ``pgvector/pgvector:pg16`` image (the image of the compose stack).

Tests that use ``migrated_db`` are skipped when neither is available. The migration SQL files are applied in
directory order, which is what ``prisma migrate deploy`` does, minus its bookkeeping table. Drift between the
Prisma schema and the migrations is checked separately by the ``migration-drift`` CI job.

``migrated_db`` is a ``postgresql://`` URL of the migrator (a superuser here). ``app_db`` is a URL for a fresh
login role that is a member of ``apex_app``, the role the application uses in production.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "web" / "prisma" / "migrations"
ADMIN_URL_ENV = "APEX_TEST_PG_ADMIN_URL"


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


def postgres_available() -> bool:
    return bool(os.environ.get(ADMIN_URL_ENV)) or docker_available()


def with_database(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


def with_credentials(url: str, user: str, password: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or "localhost"
    netloc = f"{quote(user)}:{quote(password)}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def apply_migrations(url: str) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(url, autocommit=True) as conn:
        for directory in sorted(p for p in MIGRATIONS_DIR.iterdir() if p.is_dir()):
            conn.execute((directory / "migration.sql").read_text(encoding="utf-8"))  # type: ignore[arg-type]
            applied.append(directory.name)
    return applied


@pytest.fixture(scope="module")
def migrated_db() -> Iterator[str]:
    admin_url = os.environ.get(ADMIN_URL_ENV)
    if admin_url:
        name = f"apex_test_{uuid4().hex[:12]}"
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{name}"')  # type: ignore[arg-type]
        url = with_database(admin_url, name)
        try:
            apply_migrations(url)
            yield url
        finally:
            with psycopg.connect(admin_url, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')  # type: ignore[arg-type]
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as pg:
        url = pg.get_connection_url()
        apply_migrations(url)
        yield url


@pytest.fixture(scope="module")
def app_db(migrated_db: str) -> Iterator[str]:
    """A login role in ``apex_app``: no superuser, no table ownership, no BYPASSRLS."""
    role = f"apex_app_test_{uuid4().hex[:8]}"
    password = uuid4().hex
    with psycopg.connect(migrated_db, autocommit=True) as admin:
        admin.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{password}' IN ROLE apex_app")  # type: ignore[arg-type]
    try:
        yield with_credentials(migrated_db, role, password)
    finally:
        with psycopg.connect(migrated_db, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = %s", [role]
            )
            admin.execute(f"DROP ROLE IF EXISTS {role}")  # type: ignore[arg-type]
