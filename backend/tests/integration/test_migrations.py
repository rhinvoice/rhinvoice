from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, select

from rhinvoice.infrastructure.db.migrate import downgrade, upgrade
from rhinvoice.infrastructure.db.tables import metadata, text_templates


def test_schema_matches_metadata(migrated_engine: Engine) -> None:
    """Every change to tables.py must come with a migration."""
    with migrated_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, metadata) == []


def test_migrations_round_trip(database_url: str, migrated_engine: Engine) -> None:
    downgrade(database_url, "base")
    assert set(inspect(migrated_engine).get_table_names()) == {"alembic_version"}
    upgrade(database_url)
    names = set(inspect(migrated_engine).get_table_names())
    assert {table.name for table in metadata.sorted_tables} <= names
    # Version 0006 brings ready-made text templates in German and English.
    with migrated_engine.connect() as connection:
        rows = connection.execute(
            select(
                text_templates.c.document_type,
                text_templates.c.language,
                text_templates.c.kind,
                text_templates.c.position,
                text_templates.c.is_default,
            ),
        ).all()
    assert len(rows) == 13
    assert {(row.document_type, row.language) for row in rows} == {
        ("invoice", "de"),
        ("invoice", "en"),
        ("quote", "de"),
        ("quote", "en"),
    }
    payments = sorted(
        (row.position, row.is_default)
        for row in rows
        if (row.document_type, row.language, row.kind) == ("invoice", "de", "payment")
    )
    assert payments == [(0, True), (1, True), (2, False)]
