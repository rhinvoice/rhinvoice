"""The import against PostgreSQL: duplicates by name, the test run's rollback, templates."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.catalog.handlers import ArticleHandlers, SaveArticle
from rhinvoice.application.common import AddressInput
from rhinvoice.application.company.handlers import CompanyHandlers, SaveCompany
from rhinvoice.application.customer.handlers import CustomerHandlers, SaveCustomer
from rhinvoice.application.customer.ports import CustomerQuery
from rhinvoice.application.importing.fields import ImportTarget
from rhinvoice.application.importing.handlers import (
    DuplicateStrategy,
    ImportHandlers,
    ImportRequest,
    RowStatus,
    SaveTemplate,
)
from rhinvoice.application.importing.ports import ImportTemplate
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from rhinvoice.infrastructure.importing.reader import SpreadsheetReader

CLOCK = FixedClock(datetime(2026, 3, 9, 9, 0, tzinfo=UTC))
BERN = AddressInput(postal_code="3011", city="Bern", country="CH")


def handlers(engine: Engine) -> ImportHandlers:
    return ImportHandlers(
        uow=lambda: SqlUnitOfWork(engine), clock=CLOCK, reader=SpreadsheetReader()
    )


@pytest.fixture
def company(engine: Engine) -> None:
    CompanyHandlers(uow=lambda: SqlUnitOfWork(engine)).save(
        SaveCompany(
            name="Muster GmbH",
            address=BERN,
            default_currency=Currency.CHF,
            default_language=Language.DE,
        )
    )


@pytest.mark.usefixtures("company")
def test_customers_are_found_by_number_and_by_name(engine: Engine) -> None:
    customers = CustomerHandlers(uow=lambda: SqlUnitOfWork(engine), clock=CLOCK)
    customers.create(
        SaveCustomer(
            kind=CustomerKind.COMPANY, company_name="Beispiel AG", address=BERN, number="5"
        )
    )
    person = customers.create(
        SaveCustomer(kind=CustomerKind.PERSON, first_name="Anna", last_name="Muster", address=BERN)
    )
    content = (
        b"Nr;Firma;Vorname;Nachname;PLZ;Ort\n"
        b"5;Neu AG;;;3011;Bern\n"
        b";BEISPIEL ag;;;3011;Bern\n"
        b";;anna;muster;3011;Bern\n"
        b";;Anna;Muster;9000;St. Gallen\n"
    )
    run = handlers(engine).run(ImportRequest(target=ImportTarget.CUSTOMERS, content=content))
    assert [(o.status, o.number) for o in run.outcomes] == [
        (RowStatus.SKIPPED, "5"),
        (RowStatus.SKIPPED, "5"),
        (RowStatus.SKIPPED, person.number),
        (RowStatus.NEW, "1002"),
    ]


@pytest.mark.usefixtures("company")
def test_the_test_run_rolls_back_numbers_and_rows(engine: Engine) -> None:
    content = b"Firma;PLZ Ort\nA AG;3000 Bern\nB AG;3000 Bern\n"
    request = ImportRequest(target=ImportTarget.CUSTOMERS, content=content)
    first = handlers(engine).run(request)
    second = handlers(engine).run(request)
    assert (
        [o.number for o in first.outcomes]
        == [o.number for o in second.outcomes]
        == [
            "1001",
            "1002",
        ]
    )
    customers = CustomerHandlers(uow=lambda: SqlUnitOfWork(engine), clock=CLOCK)
    assert customers.search(CustomerQuery()).items == []
    handlers(engine).run(ImportRequest(target=ImportTarget.CUSTOMERS, content=content, commit=True))
    saved = customers.search(CustomerQuery()).items
    assert [(c.number, c.company_name) for c in saved] == [("1001", "A AG"), ("1002", "B AG")]


@pytest.mark.usefixtures("company")
def test_articles_are_found_by_number_and_by_name(engine: Engine) -> None:
    articles = ArticleHandlers(uow=lambda: SqlUnitOfWork(engine), clock=CLOCK)
    existing = articles.create(
        SaveArticle(name="Beratung", number="A1", prices={Currency.EUR: "100"})
    )
    content = b"Bezeichnung;Preis\nberatung;120\nSupport;50\n"
    run = handlers(engine).run(
        ImportRequest(
            target=ImportTarget.ARTICLES,
            content=content,
            duplicates=DuplicateStrategy.UPDATE,
            commit=True,
        )
    )
    assert [(o.status, o.number) for o in run.outcomes] == [
        (RowStatus.UPDATED, "A1"),
        (RowStatus.NEW, "1"),
    ]
    updated = articles.get(existing.id)
    assert updated.prices == {Currency.EUR: Decimal(100), Currency.CHF: Decimal(120)}
    numbered = handlers(engine).run(
        ImportRequest(target=ImportTarget.ARTICLES, content=b"Nr;Bezeichnung\nA1;X\n")
    )
    assert numbered.outcomes[0].status is RowStatus.SKIPPED


def test_templates(engine: Engine) -> None:
    imports = handlers(engine)
    saved = imports.save_template(
        SaveTemplate(target=ImportTarget.ARTICLES, name="Webshop", columns={"name": "Titel"})
    )
    imports.save_template(
        SaveTemplate(target=ImportTarget.ARTICLES, name="alt", columns={"price": "VK"})
    )
    assert [t.name for t in imports.templates(ImportTarget.ARTICLES)] == ["alt", "Webshop"]
    assert imports.templates(ImportTarget.CUSTOMERS) == []
    assert imports.templates(ImportTarget.ARTICLES)[1] == saved
    imports.delete_template(saved.id)
    assert [t.name for t in imports.templates(ImportTarget.ARTICLES)] == ["alt"]
    # The database refuses a second template of the same name, too.
    with SqlUnitOfWork(engine) as uow, pytest.raises(IntegrityError):
        uow.import_templates.add(
            ImportTemplate(
                id=new_id(),
                target=ImportTarget.ARTICLES,
                name="alt",
                columns={"name": "X"},
                created_at=CLOCK.now(),
            )
        )
    with SqlUnitOfWork(engine) as uow:
        assert uow.import_templates.get(new_id()) is None
