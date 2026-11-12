from dataclasses import replace
from uuid import UUID

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, inspect, select, text

from rhinvoice.application.catalog.handlers import ArticleHandlers, SaveArticle
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.domain.company.print_layout import (
    DEFAULT_INFO_BLOCK,
    InfoEntry,
    NamedLayout,
    PrintLayout,
    PrintTemplate,
)
from rhinvoice.domain.document.document import DocumentType, FieldValue
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.infrastructure.db.migrate import downgrade, upgrade
from rhinvoice.infrastructure.db.tables import dunning_levels, metadata, text_templates
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from tests.helpers import raises_exactly
from tests.integration.test_document_persistence import setup
from tests.integration.test_recurring_persistence import TEMPLATE, plan

__all__ = ["setup"]  # the fixture of the document tests


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


def test_pass_through_items_fall_back_to_exempt_on_a_downgrade(
    database_url: str, engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    """Drafts, articles and recurring plans; the plan's other lines and their order stay."""
    documents, customer, clock = setup
    fee = LineInput(
        kind=LineKind.ITEM,
        description="Gebühr",
        unit_price="80",
        tax_category=TaxCategory.PASS_THROUGH,
    )
    draft = documents.create(
        DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(fee,))
    ).document.id
    ArticleHandlers(uow=lambda: SqlUnitOfWork(engine), clock=clock).create(
        SaveArticle(name="Gebühr", tax_category=TaxCategory.PASS_THROUGH)
    )
    template = replace(TEMPLATE, lines=(*TEMPLATE.lines, fee.to_domain(2)))
    with SqlUnitOfWork(engine) as uow:
        uow.recurring.add(replace(plan(customer, "Wartung", clock.today()), template=template))
        uow.recurring.add(plan(customer, "Hosting", clock.today()))
        uow.commit()
    downgrade(database_url, "0022")
    try:
        with engine.connect() as connection:
            lines = connection.execute(
                text("SELECT tax_category FROM document_lines WHERE document_id = :id"),
                {"id": draft},
            ).scalars()
            assert list(lines) == ["exempt"]
            articles = connection.execute(text("SELECT tax_category FROM articles")).scalars()
            assert list(articles) == ["exempt"]
            plans = {
                row.name: row.categories
                for row in connection.execute(
                    text(
                        "SELECT name, jsonb_path_query_array(template, '$.lines[*].tax_category')"
                        " AS categories FROM recurring_plans"
                    )
                )
            }
    finally:
        upgrade(database_url)
    assert plans == {
        "Wartung": ["standard", "reduced", "exempt"],
        "Hosting": ["standard", "reduced"],
    }


def test_removed_files_are_forgotten_on_a_downgrade_of_drafts_only(
    database_url: str, engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    """Older versions cannot read the event: issued documents keep it, so the downgrade stops."""
    documents, customer, _ = setup
    line = LineInput(kind=LineKind.ITEM, description="Beratung", unit_price="80")

    def with_removed_file() -> UUID:
        draft = documents.create(
            DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(line,))
        ).document.id
        documents.add_file(draft, "Notar.pdf", b"%PDF-1.4 notary")
        [attachment] = documents.attachments(draft)
        documents.remove_file(draft, attachment.id)
        return draft

    def removed_events(connection: Connection) -> int:
        count = connection.execute(
            text("SELECT count(*) FROM document_events WHERE kind = 'file_removed'")
        ).scalar_one()
        return int(count)

    with_removed_file()
    downgrade(database_url, "0022")
    try:
        with engine.connect() as connection:
            assert removed_events(connection) == 0
    finally:
        upgrade(database_url)
    documents.issue(with_removed_file())
    with raises_exactly(
        RuntimeError, "issued documents record removed files: they need version 0.10 or later"
    ):
        downgrade(database_url, "0022")
    with engine.connect() as connection:
        assert removed_events(connection) == 1


def use_layout(engine: Engine, layout: PrintLayout) -> None:
    """Give the default print layout these settings."""
    with SqlUnitOfWork(engine) as uow:
        [default] = [named for named in uow.print_layouts.list() if named.is_default]
        uow.print_layouts.update(replace(default, layout=layout))
        uow.commit()


def test_the_saved_layout_becomes_the_default_one_and_back(
    database_url: str, engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    """0026 names the layout saved so far "Standard"; a downgrade keeps the default one."""
    documents, customer, _ = setup
    classic = PrintLayout(template=PrintTemplate.CLASSIC, contact=True)
    use_layout(engine, classic)
    with SqlUnitOfWork(engine) as uow:
        uow.print_layouts.add(NamedLayout(new_id(), "Behörden", PrintLayout()))
        uow.commit()
    line = LineInput(kind=LineKind.ITEM, description="Beratung", unit_price="80")
    documents.create(DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(line,)))
    downgrade(database_url, "0025")
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT template, contact FROM print_layout")).all()
            assert [tuple(row) for row in rows] == [("classic", True)]
            assert "print_layouts" not in inspect(connection).get_table_names()
    finally:
        upgrade(database_url)
    with SqlUnitOfWork(engine) as uow:
        assert [
            (named.name, named.is_default, named.layout) for named in uow.print_layouts.list()
        ] == [("Standard", True, classic)]
    # Without a saved layout the program's defaults, as documents printed before.
    with engine.begin() as connection:
        connection.execute(text("UPDATE customers SET print_layout_id = NULL"))
    downgrade(database_url, "0025")
    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM print_layout"))
    finally:
        upgrade(database_url)
    with SqlUnitOfWork(engine) as uow:
        assert [(named.name, named.layout) for named in uow.print_layouts.list()] == [
            ("Standard", PrintLayout())
        ]


def test_field_values_go_on_a_downgrade_of_drafts_only(
    database_url: str, engine: Engine, setup: tuple[DocumentHandlers, UUID, FixedClock]
) -> None:
    """Drafts and plans lose their values; an issued document that prints one stops it."""
    documents, customer, clock = setup
    line = LineInput(kind=LineKind.ITEM, description="Beratung", unit_price="80")
    values = (("project", "Website"),)
    documents.create(
        DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(line,), fields=values)
    )
    template = replace(TEMPLATE, fields=(FieldValue("contract", "V-7"),))
    with SqlUnitOfWork(engine) as uow:
        uow.recurring.add(replace(plan(customer, "Wartung", clock.today()), template=template))
        uow.commit()
    use_layout(engine, PrintLayout(info_block=(*DEFAULT_INFO_BLOCK, InfoEntry("project"))))
    downgrade(database_url, "0024")
    try:
        with engine.connect() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("documents")}
            assert "fields" not in columns
            plans = connection.execute(
                text("SELECT template ? 'fields' FROM recurring_plans")
            ).scalars()
            assert list(plans) == [False]
    finally:
        upgrade(database_url)
    # An issued document with the old rows and no values does not stop it.
    documents.issue(
        documents.create(
            DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(line,))
        ).document.id
    )
    use_layout(engine, PrintLayout())
    downgrade(database_url, "0024")
    upgrade(database_url)
    created = documents.create(
        DocumentType.INVOICE, DraftInput(customer_id=customer, lines=(line,), fields=values)
    )
    documents.issue(created.document.id)
    with raises_exactly(
        RuntimeError,
        "issued documents print fields or other rows: they need the version that added them",
    ):
        downgrade(database_url, "0024")
