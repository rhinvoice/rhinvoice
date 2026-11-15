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
from rhinvoice.infrastructure.db.repositories.masterdata import SqlPrintLayoutRepository
from rhinvoice.infrastructure.db.repositories.units import SqlUnitRepository
from rhinvoice.infrastructure.db.tables import metadata
from rhinvoice.infrastructure.db.uow import make_engine
from tests.unit.application.fakes import STANDARD_LAYOUT
from tests.unit.domain import factories

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
    # Also before: a test of the migrations may have seeded the units under ids of its own,
    # while the tests know them by those of factories.unit_id.
    _reset(migrated_engine)
    yield migrated_engine
    _reset(migrated_engine)


def _reset(engine: Engine) -> None:
    """Empty every table and add what each installation has from its migrations."""
    tables = ", ".join(f'"{table.name}"' for table in metadata.sorted_tables)
    with engine.begin() as connection:
        # The archive triggers forbid TRUNCATE; tests clean up as the replication role,
        # which skips them (the test database user is a superuser).
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        # Like migration 0026: every installation has its default print layout.
        SqlPrintLayoutRepository(connection).add(STANDARD_LAYOUT)
        # Like migration 0029: every installation starts with the units of before.
        for unit in factories.units().values():
            SqlUnitRepository(connection).add(unit)
