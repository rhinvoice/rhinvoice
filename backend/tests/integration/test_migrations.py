from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, select, text

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
    """Version 0019 fills the new columns of saved levels with its own copy of the texts.

    The check does not compare with the domain's texts, which may be reworded later.
    """
    downgrade(database_url, "0018")
    with migrated_engine.begin() as connection:
        for level in (1, 2, 3):
            connection.execute(
                text(
                    "INSERT INTO dunning_levels (level, days_after_due, payment_days, fee,"
                    " text_de, text_en) VALUES (:level, 10, 10, 0, 'Bitte zahlen', 'Please pay')"
                ).bindparams(level=level)
            )
    upgrade(database_url)
    with migrated_engine.begin() as connection:
        rows = connection.execute(select(dunning_levels).order_by(dunning_levels.c.level)).all()
        connection.execute(dunning_levels.delete())
    assert [(row.level, row.text_de, row.text_en) for row in rows] == [
        (level, "Bitte zahlen", "Please pay") for level in (1, 2, 3)
    ]
    for row in rows:
        # Each level reads in its language and names the new due date.
        assert "{faellig}" in row.text_fr
        assert "{faellig}" in row.text_it
        assert row.text_fr != row.text_it
    assert len({row.text_fr for row in rows}) == len({row.text_it for row in rows}) == 3
    assert "facture" in rows[1].text_fr
    assert "fattura" in rows[1].text_it
