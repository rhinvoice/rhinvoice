"""Shared PostgreSQL fixtures (started lazily, only for tests that need them).

A throwaway PostgreSQL container is started once per test session via
testcontainers. Set ``TEST_DATABASE_URL`` to use an existing (empty!) database
instead, e.g. a service container in CI.
"""

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from testcontainers.community.postgres import PostgresContainer

from rhinvoice.infrastructure.db.migrate import upgrade
from rhinvoice.infrastructure.db.tables import metadata
from rhinvoice.infrastructure.db.uow import make_engine

POSTGRES_IMAGE = "postgres:17-alpine"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    configured = os.environ.get("TEST_DATABASE_URL")
    if configured:
        yield configured
        return
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_engine(database_url: str) -> Iterator[Engine]:
    upgrade(database_url)
    engine = make_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def engine(migrated_engine: Engine) -> Iterator[Engine]:
    yield migrated_engine
    tables = ", ".join(f'"{table.name}"' for table in metadata.sorted_tables)
    with migrated_engine.begin() as connection:
        # The archive triggers forbid TRUNCATE; tests clean up as the replication role,
        # which skips them (the test database user is a superuser).
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
