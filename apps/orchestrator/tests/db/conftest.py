"""A fresh Postgres database with every Prisma migration applied (D2-03).

Two ways to get a server, in this order:
1. ``APEX_TEST_PG_ADMIN_URL``: a superuser URL of a running Postgres 16 with pgvector. A throwaway database is
   created on it for the test module and dropped afterwards. Useful without Docker.
2. Testcontainers with the ``pgvector/pgvector:pg16`` image (the image of the compose stack).

Tests that use ``migrated_db`` are skipped when neither is available. The migration SQL files are applied in
directory order, which is what ``prisma migrate deploy`` does, minus its bookkeeping table. Drift between the
Prisma schema and the migrations is checked separately by the ``migration-drift`` CI job.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "web" / "prisma" / "migrations"
ADMIN_URL_ENV = "APEX_TEST_PG_ADMIN_URL"


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


def postgres_available() -> bool:
    return bool(os.environ.get(ADMIN_URL_ENV)) or docker_available()


def apply_migrations(conninfo: str) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(conninfo, autocommit=True) as conn:
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
        conninfo = make_conninfo(admin_url, dbname=name)
        try:
            apply_migrations(conninfo)
            yield conninfo
        finally:
            with psycopg.connect(admin_url, autocommit=True) as admin:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')  # type: ignore[arg-type]
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as pg:
        conninfo = pg.get_connection_url()
        apply_migrations(conninfo)
        yield conninfo
