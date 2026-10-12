"""Programmatic access to the Alembic migrations shipped with the package."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, inspect, text

MIGRATIONS = Path(__file__).parent / "migrations"


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade(database_url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(database_url), revision)


def downgrade(database_url: str, revision: str) -> None:
    command.downgrade(alembic_config(database_url), revision)


class NewerDatabaseError(Exception):
    """The database was migrated by a newer Rhinvoice than this one."""

    def __init__(self, revision: str, head: str) -> None:
        super().__init__(
            f"the database was set up by a newer version of Rhinvoice (schema {revision}); "
            f"this version knows schemas up to {head}. Start the newer version "
            "(docker compose up -d --build, or its image) or restore a backup of this version."
        )
        self.revision = revision
        self.head = head


def require_known_schema(database_url: str) -> None:
    """Refuse a database whose schema this version does not know.

    An older app on a newer schema would write rows the newer version reads
    differently; better to stop with a clear message than to fail later.
    """
    scripts = ScriptDirectory.from_config(alembic_config(database_url))
    known = {script.revision for script in scripts.walk_revisions()}
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
    if current is not None and current not in known:
        raise NewerDatabaseError(current, str(scripts.get_current_head()))


class NotADemoDatabaseError(Exception):
    """A demo reset was asked for a database that is not a demo database."""


DEMO_MARKER = "rhinvoice public demo: emptied and filled again on every reset"
"""The comment on a demo database; only a database carrying it may be reset again."""


def reset_demo_database(database_url: str, demo_email: str) -> None:
    """Drop all data and rebuild the schema, for a public demo installation only.

    The first reset needs an empty database or one that knows only the demo login, and
    marks the database as a demo (a comment on the database, kept by the reset). Later
    resets go by the mark, so a user who slipped in never blocks the demo; a database
    with real data has no mark and is never wiped.
    """
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            name = connection.execute(text("SELECT current_database()")).scalar_one()
            comment = connection.execute(
                text(
                    "SELECT shobj_description(oid, 'pg_database') FROM pg_database "
                    "WHERE datname = current_database()"
                )
            ).scalar_one()
            if comment != DEMO_MARKER:
                _require_only_demo_users(connection, demo_email)
            # Waiting longer would stall every request behind the lock; the next run retries.
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            quoted = connection.dialect.identifier_preparer.quote(name)
            # COMMENT takes no parameters; the marker is a constant without quotes.
            connection.execute(text(f"COMMENT ON DATABASE {quoted} IS '{DEMO_MARKER}'"))
    finally:
        engine.dispose()
    upgrade(database_url)


def _require_only_demo_users(connection: Connection, demo_email: str) -> None:
    if not inspect(connection).has_table("users"):
        return
    others = connection.execute(
        text("SELECT count(*) FROM users WHERE email <> :email"), {"email": demo_email}
    ).scalar_one()
    if others:
        msg = (
            f"refusing to reset: the database has {others} user(s) besides {demo_email} "
            "and is not marked as a demo; RHINVOICE_DEMO is meant for an empty demo database"
        )
        raise NotADemoDatabaseError(msg)
