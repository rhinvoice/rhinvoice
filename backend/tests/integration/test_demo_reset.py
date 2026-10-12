"""Resetting a public demo: a fresh database every time, never a real installation."""

import re
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, make_url, text

from rhinvoice.api import cli
from rhinvoice.api.container import build_container
from rhinvoice.api.settings import Settings
from rhinvoice.application.demo.handlers import DEMO_EMAIL
from rhinvoice.application.identity.handlers import CreateUser
from rhinvoice.domain.shared.country import Country
from rhinvoice.infrastructure.db.migrate import (
    DEMO_MARKER,
    NotADemoDatabaseError,
    reset_demo_database,
    upgrade,
)

DEMO_DATABASE = "rhinvoice_demo_reset"


@pytest.fixture
def demo_url(migrated_engine: Engine, database_url: str) -> Iterator[str]:
    """Give the test a database of its own: the reset drops the whole schema."""
    admin = migrated_engine.execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {DEMO_DATABASE}"))
        connection.execute(text(f"CREATE DATABASE {DEMO_DATABASE}"))
    yield make_url(database_url).set(database=DEMO_DATABASE).render_as_string(hide_password=False)
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE {DEMO_DATABASE} WITH (FORCE)"))


def count(url: str, table: str) -> int:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            query = text(f"SELECT count(*) FROM {table}")  # noqa: S608 - names from the tests
            return int(connection.execute(query).scalar_one())
    finally:
        engine.dispose()


def test_a_demo_starts_afresh_on_every_reset(demo_url: str) -> None:
    settings = Settings(database_url=demo_url, demo=True, demo_country=Country.DE)
    container = build_container(settings)
    try:
        cli.reset_demo(settings, container)
        customers = count(demo_url, "customers")
        assert customers > 0
        assert count(demo_url, "users") == 1
        assert container.onboarding.status().dismissed
        # Visitors changed things in the meantime: the next reset forgets them.
        engine = create_engine(demo_url)
        with engine.begin() as connection:
            connection.execute(text("UPDATE company SET name = 'Visitor & Co'"))
        engine.dispose()
        cli.reset_demo(settings, container)
        assert count(demo_url, "customers") == customers
        with engine.connect() as connection:
            name = connection.execute(text("SELECT name FROM company")).scalar_one()
            country = connection.execute(text("SELECT country FROM company")).scalar_one()
        engine.dispose()
        assert (name, country) == ("Muster Webdesign GmbH", "DE")
    finally:
        container.engine.dispose()


def add_user(url: str, email: str) -> None:
    container = build_container(Settings(database_url=url))
    try:
        container.identity.create_user(
            CreateUser(email=email, display_name="Someone", password="x" * 12)
        )
    finally:
        container.engine.dispose()


def test_a_database_with_real_users_is_never_reset(demo_url: str) -> None:
    upgrade(demo_url)
    add_user(demo_url, "anna@example.com")
    with pytest.raises(NotADemoDatabaseError, match=re.escape("1 user(s) besides demo@rhinvoice")):
        reset_demo_database(demo_url, DEMO_EMAIL)
    assert count(demo_url, "users") == 1


def test_a_demo_database_of_an_earlier_version_is_taken_over(demo_url: str) -> None:
    """Unmarked, but only the demo login: the first reset may go ahead and marks it."""
    upgrade(demo_url)
    add_user(demo_url, DEMO_EMAIL)
    reset_demo_database(demo_url, DEMO_EMAIL)
    assert count(demo_url, "users") == 0


def test_a_user_who_slipped_into_a_demo_never_blocks_it(demo_url: str) -> None:
    reset_demo_database(demo_url, DEMO_EMAIL)
    add_user(demo_url, "intruder@example.com")
    # The database is marked as a demo: the reset goes on and forgets the intruder.
    reset_demo_database(demo_url, DEMO_EMAIL)
    assert count(demo_url, "users") == 0
    engine = create_engine(demo_url)
    with engine.connect() as connection:
        comment = connection.execute(
            text(
                "SELECT shobj_description(oid, 'pg_database') FROM pg_database "
                "WHERE datname = current_database()"
            )
        ).scalar_one()
    engine.dispose()
    assert comment == DEMO_MARKER
