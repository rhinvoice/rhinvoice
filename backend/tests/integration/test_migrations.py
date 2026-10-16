from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, select, text

from rhinvoice.domain.dunning.reminder import FRENCH_TEXTS, ITALIAN_TEXTS
from rhinvoice.infrastructure.db.migrate import downgrade, upgrade
from rhinvoice.infrastructure.db.tables import dunning_levels, metadata, text_templates


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
    # Version 0006 brings ready-made text templates in German and English, 0019 in French
    # and Italian.
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
    assert len(rows) == 27  # 7 per language; English has no "net" payment term
    assert {(row.document_type, row.language) for row in rows} == {
        (document_type, language)
        for document_type in ("invoice", "quote")
        for language in ("de", "en", "fr", "it")
    }
    for language in ("de", "fr", "it"):
        payments = sorted(
            (row.position, row.is_default)
            for row in rows
            if (row.document_type, row.language, row.kind) == ("invoice", language, "payment")
        )
        assert payments == [(0, True), (1, True), (2, False)]


def test_saved_dunning_levels_get_french_and_italian_texts(
    database_url: str, migrated_engine: Engine
) -> None:
    downgrade(database_url, "0018")
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO dunning_levels (level, days_after_due, payment_days, fee, text_de,"
                " text_en) VALUES (2, 10, 10, 0, 'Bitte zahlen', 'Please pay')"
            )
        )
    upgrade(database_url)
    with migrated_engine.begin() as connection:
        row = connection.execute(select(dunning_levels)).one()
        connection.execute(dunning_levels.delete())
    assert (row.text_de, row.text_en) == ("Bitte zahlen", "Please pay")
    assert (row.text_fr, row.text_it) == (FRENCH_TEXTS[2], ITALIAN_TEXTS[2])
