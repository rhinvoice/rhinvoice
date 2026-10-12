"""Importing customers and articles: test run, duplicates, errors per row, templates."""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.application.importing.fields import ImportTarget
from rhinvoice.application.importing.handlers import (
    DEMO_IMPORT_LIMITS,
    DuplicateStrategy,
    ImportHandlers,
    ImportLimits,
    ImportRequest,
    RowProblem,
    RowStatus,
    SaveTemplate,
)
from rhinvoice.application.importing.ports import ImportTable
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories


class SemicolonReader:
    """Reads "a;b" lines; the real reader (infrastructure) has its own tests."""

    def read(self, content: bytes) -> ImportTable:
        rows = list(csv.reader(io.StringIO(content.decode()), delimiter=";"))
        return ImportTable(
            headers=tuple(rows[0]), rows=tuple(tuple(r) for r in rows[1:]), file_type="csv"
        )


@pytest.fixture
def handlers(store: Store, clock: FixedClock) -> ImportHandlers:
    store.company = factories.company()
    return ImportHandlers(
        uow=lambda: InMemoryUnitOfWork(store), clock=clock, reader=SemicolonReader()
    )


def lines(*rows: str) -> bytes:
    return "\n".join(rows).encode()


CUSTOMERS = lines(
    "KdNr;Firma;Vorname;Nachname;Strasse;PLZ_Ort;Land;E-Mail;UID",
    "10042;Bergbahnen Muster AG;;;Dorfstrasse 1;CH-9470 Buchs SG;;info@example.com;CHE-123.456.788",
    ";;Anna;Muster;Bahnhofstrasse 5a;6850 Dornbirn;Österreich;;",
    "10017;Holzbau Beispiel GmbH;;;Feldweg 3;;;;",
)


def customers_request(**overrides: object) -> ImportRequest:
    values: dict[str, object] = {"target": ImportTarget.CUSTOMERS, "content": CUSTOMERS}
    values.update(overrides)
    return ImportRequest(**values)  # type: ignore[arg-type]  # test builder


def test_a_test_run_reports_every_row_and_changes_nothing(
    handlers: ImportHandlers, store: Store
) -> None:
    run = handlers.run(customers_request())
    assert not run.committed
    assert run.mapping == {
        "number": 0,
        "company_name": 1,
        "first_name": 2,
        "last_name": 3,
        "street": 4,
        "postal_city": 5,
        "country": 6,
        "email": 7,
        "vat_number": 8,
    }
    assert [(o.row, o.status, o.number, o.name, o.detail) for o in run.outcomes] == [
        (2, RowStatus.NEW, "10042", "Bergbahnen Muster AG", "9470 Buchs SG"),
        (3, RowStatus.NEW, "1001", "Anna Muster", "6850 Dornbirn"),
        (4, RowStatus.ERROR, "10017", "Holzbau Beispiel GmbH", ""),
    ]
    problem = run.outcomes[2].problem
    assert problem is not None
    assert problem.field == "postal_code"
    assert (run.count(RowStatus.NEW), run.count(RowStatus.ERROR)) == (2, 1)
    assert store.customers == {}


def test_the_import_saves_the_rows_without_errors(handlers: ImportHandlers, store: Store) -> None:
    run = handlers.run(customers_request(commit=True))
    assert run.committed
    saved = {customer.number: customer for customer in store.customers.values()}
    assert set(saved) == {"10042", "1001"}
    company = saved["10042"]
    assert company.kind is CustomerKind.COMPANY
    assert (company.address.street, company.address.house_number) == ("Dorfstrasse", "1")
    assert (company.address.postal_code, company.address.city) == ("9470", "Buchs SG")
    assert company.address.country == CountryCode("CH")
    assert str(company.email) == "info@example.com"
    assert str(company.vat_number) == "CHE-123.456.788"
    assert company.created_at == NOW
    person = saved["1001"]
    assert person.kind is CustomerKind.PERSON
    assert (person.first_name, person.last_name) == ("Anna", "Muster")
    assert (person.address.street, person.address.house_number) == ("Bahnhofstrasse", "5a")
    assert person.address.country == CountryCode("AT")


def test_the_country_prefix_of_the_postal_code_counts_when_the_country_is_empty(
    handlers: ImportHandlers, store: Store
) -> None:
    content = lines("Firma;PLZ_Ort", "Alpenholz GmbH;A-6850 Dornbirn", "Muster AG;9000 St. Gallen")
    handlers.run(customers_request(content=content, commit=True))
    countries = {c.company_name: c.address.country.value for c in store.customers.values()}
    # Without a country the company's own country is assumed.
    assert countries == {"Alpenholz GmbH": "AT", "Muster AG": "CH"}


def test_separate_postal_code_city_and_house_number_columns(
    handlers: ImportHandlers, store: Store
) -> None:
    content = lines(
        "Firma;Strasse;Hausnummer;PLZ;Ort;Telefon;Gruppe;Notiz;Währung;Sprache;Rabatt;"
        "Zahlungsziel;Steuerbefreit;Anrede;Kontaktperson;Adresszusatz",
        "Muster AG;Dorfstrasse;1 a;9470;Buchs SG;+41 81 000 00 00;Stamm;Seit 2014;EUR;Englisch;"
        "5 %;20;ja;Firma;Frau Beispiel;Postfach 12",
    )
    handlers.run(customers_request(content=content, commit=True))
    [customer] = store.customers.values()
    assert (customer.address.street, customer.address.house_number) == ("Dorfstrasse", "1 a")
    assert customer.address.supplement == "Postfach 12"
    assert (customer.phone, customer.group, customer.note) == (
        "+41 81 000 00 00",
        "Stamm",
        "Seit 2014",
    )
    assert customer.default_currency is Currency.EUR
    assert customer.default_language is Language.EN
    assert customer.default_discount == Decimal(5)
    assert customer.payment_terms_days == 20
    assert customer.tax_exempt
    assert (customer.salutation, customer.contact_person) == ("Firma", "Frau Beispiel")


def test_duplicates_are_skipped_by_default(handlers: ImportHandlers, store: Store) -> None:
    existing = factories.customer(number="10042", company_name="Alter Name AG")
    store.customers[existing.id] = existing
    run = handlers.run(customers_request(commit=True))
    first = run.outcomes[0]
    assert (first.status, first.number, first.name) == (RowStatus.SKIPPED, "10042", "Alter Name AG")
    assert store.customers[existing.id] == existing
    assert len(store.customers) == 2


def test_duplicates_without_a_number_are_found_by_name_and_postal_code(
    handlers: ImportHandlers, store: Store
) -> None:
    existing = factories.customer(
        number="7",
        kind=CustomerKind.PERSON,
        company_name="",
        first_name="Anna",
        last_name="MUSTER",
        address=factories.address(postal_code="6850", city="Dornbirn", country=CountryCode("AT")),
    )
    store.customers[existing.id] = existing
    run = handlers.run(customers_request())
    assert (run.outcomes[1].status, run.outcomes[1].number) == (RowStatus.SKIPPED, "7")


def test_updating_duplicates_keeps_what_the_file_does_not_say(
    handlers: ImportHandlers, store: Store
) -> None:
    existing = factories.customer(
        number="10042",
        company_name="Alter Name AG",
        phone="+41 81 111 11 11",
        note="Wichtig",
        default_language=Language.EN,
    )
    store.customers[existing.id] = existing
    run = handlers.run(customers_request(duplicates=DuplicateStrategy.UPDATE, commit=True))
    assert run.outcomes[0].status is RowStatus.UPDATED
    updated = store.customers[existing.id]
    assert updated.company_name == "Bergbahnen Muster AG"
    assert (updated.address.street, updated.address.city) == ("Dorfstrasse", "Buchs SG")
    assert (updated.phone, updated.note) == ("+41 81 111 11 11", "Wichtig")
    assert updated.default_language is Language.EN
    assert (updated.created_at, updated.number) == (existing.created_at, "10042")


def test_updating_keeps_the_country_and_address_parts_the_file_leaves_empty(
    handlers: ImportHandlers, store: Store
) -> None:
    existing = factories.customer(
        number="5",
        company_name="Muster AG",
        address=factories.address(
            street="Alte Gasse",
            house_number="9",
            postal_code="6850",
            city="Dornbirn",
            country=CountryCode("AT"),
            supplement="Hinterhaus",
        ),
        delivery_address=factories.address(city="Lieferort"),
    )
    store.customers[existing.id] = existing
    content = lines("Nr;Firma;Ort", "5;Muster AG;Bregenz")
    handlers.run(
        customers_request(content=content, duplicates=DuplicateStrategy.UPDATE, commit=True)
    )
    address = store.customers[existing.id].address
    assert (address.street, address.house_number, address.postal_code) == (
        "Alte Gasse",
        "9",
        "6850",
    )
    assert (address.city, address.country.value, address.supplement) == (
        "Bregenz",
        "AT",
        "Hinterhaus",
    )
    delivery = store.customers[existing.id].delivery_address
    assert delivery is not None
    assert delivery.city == "Lieferort"


def test_creating_duplicates_anew_gives_them_a_free_number(
    handlers: ImportHandlers, store: Store
) -> None:
    existing = factories.customer(number="10042")
    store.customers[existing.id] = existing
    run = handlers.run(customers_request(duplicates=DuplicateStrategy.CREATE, commit=True))
    assert [(o.status, o.number) for o in run.outcomes[:2]] == [
        (RowStatus.NEW, "1001"),
        (RowStatus.NEW, "1002"),
    ]
    assert len(store.customers) == 3


def test_a_row_repeating_an_earlier_row_counts_as_duplicate(handlers: ImportHandlers) -> None:
    content = lines("Nr;Firma;Ort;PLZ", "1;Muster AG;Bern;3000", "1;Muster AG;Bern;3000")
    run = handlers.run(customers_request(content=content))
    assert [o.status for o in run.outcomes] == [RowStatus.NEW, RowStatus.SKIPPED]


def test_rows_with_invalid_values_report_field_and_reason(handlers: ImportHandlers) -> None:
    content = lines(
        "Firma;Ort;PLZ;E-Mail;Land;Zahlungsziel",
        "Muster AG;Bern;3000;keine-mail;;",
        "Muster AG;Bern;3000;;Atlantis;",
        "Muster AG;Bern;3000;;;bald",
        ";Bern;3000;;;",
    )
    run = handlers.run(customers_request(content=content))
    problems = [o.problem for o in run.outcomes]
    assert [p.field for p in problems if p is not None] == [
        "email",
        "country",
        "payment_terms_days",
        "last_name",
    ]
    assert run.outcomes[0] == run.outcomes[0].__class__(
        row=2,
        status=RowStatus.ERROR,
        number="",
        name="Muster AG",
        detail="",
        problem=problems[0],
    )
    assert isinstance(problems[0], RowProblem)
    # The domain's general code says whether a value is missing or wrong, with the cell.
    assert [(p.code, p.value) for p in problems if p is not None] == [
        ("invalid", "keine-mail"),
        ("invalid", "Atlantis"),
        ("invalid_number", "bald"),
        ("required", ""),
    ]


def test_problems_name_the_cell_a_field_came_from(handlers: ImportHandlers) -> None:
    content = lines("Firma;PLZ Ort;Strasse", "Muster AG;Buchs;Dorfstrasse", "Muster AG;;")
    run = handlers.run(customers_request(content=content))
    problems = [o.problem for o in run.outcomes]
    assert [(p.field, p.code, p.value) for p in problems if p is not None] == [
        ("postal_code", "invalid", "Buchs"),
        ("postal_code", "required", ""),
    ]


def test_the_mapping_can_be_given(handlers: ImportHandlers, store: Store) -> None:
    content = lines("A;B;C", "Muster AG;Bern;3000")
    run = handlers.run(
        customers_request(
            content=content, mapping={"company_name": 0, "city": 1, "postal_code": 2}, commit=True
        )
    )
    assert run.outcomes[0].status is RowStatus.NEW
    assert [c.company_name for c in store.customers.values()] == ["Muster AG"]


@pytest.mark.parametrize(
    ("mapping", "code", "message"),
    [
        (
            {"company_name": 0, "city": 1, "shoe_size": 2, "hat": 1},
            "unknown_field",
            "unknown fields: hat, shoe_size",
        ),
        ({"company_name": 0, "city": 3}, "unknown_column", "a column does not exist"),
        ({"company_name": 0, "city": -1}, "unknown_column", "a column does not exist"),
        ({"company_name": 0, "city": 0}, "column_used_twice", "a column is mapped to two fields"),
    ],
)
def test_invalid_mappings_are_rejected(
    handlers: ImportHandlers, mapping: dict[str, int], code: str, message: str
) -> None:
    content = lines("A;B;C", "Muster AG;Bern;3000")
    with raises_exactly(ValidationError, message) as caught:
        handlers.run(customers_request(content=content, mapping=mapping))
    assert (caught.value.field, caught.value.code) == ("mapping", code)


@pytest.mark.parametrize(
    ("mapping", "missing", "message"),
    [
        (
            {"city": 1, "postal_code": 2},
            (("number", "company_name", "last_name"),),
            "missing columns: number or company_name or last_name",
        ),
        (
            {},
            (("number", "company_name", "last_name"),),
            "missing columns: number or company_name or last_name",
        ),
    ],
)
def test_a_test_run_reports_missing_columns_so_they_can_be_mapped(
    handlers: ImportHandlers,
    mapping: dict[str, int],
    missing: tuple[tuple[str, ...], ...],
    message: str,
) -> None:
    content = lines("A;B;C", "Muster AG;Bern;3000")
    run = handlers.run(customers_request(content=content, mapping=mapping))
    assert (run.missing, run.outcomes, run.mapping) == (missing, (), mapping)
    assert run.table.headers == ("A", "B", "C")
    with raises_exactly(ValidationError, message) as caught:
        handlers.run(customers_request(content=content, mapping=mapping, commit=True))
    assert (caught.value.field, caught.value.code) == ("mapping", "mapping_incomplete")


def test_a_person_needs_only_the_last_name_column(handlers: ImportHandlers) -> None:
    content = lines("Nachname;PLZ Ort", "Muster;3000 Bern")
    run = handlers.run(customers_request(content=content))
    assert (run.outcomes[0].status, run.outcomes[0].name) == (RowStatus.NEW, "Muster")


def test_the_company_must_be_set_up_first(store: Store, clock: FixedClock) -> None:
    handlers = ImportHandlers(
        uow=lambda: InMemoryUnitOfWork(store), clock=clock, reader=SemicolonReader()
    )
    with raises_exactly(ConflictError, "set up the company before importing") as caught:
        handlers.run(customers_request())
    assert caught.value.code == "company_not_set_up"


def test_the_customer_since_date_comes_along(handlers: ImportHandlers, store: Store) -> None:
    content = lines("Nachname;PLZ Ort;Angelegt am", "Muster;3000 Bern;14.03.2019 10:22")
    run = handlers.run(customers_request(content=content, commit=True))
    assert run.mapping["customer_since"] == 2
    [customer] = store.customers.values()
    assert customer.created_at == datetime(2019, 3, 14, tzinfo=UTC)
    # Imported again with an update: the date of an existing customer is set as well.
    later = lines("Nachname;PLZ Ort;Angelegt am", "Muster;3000 Bern;01.02.2018")
    handlers.run(customers_request(content=later, duplicates=DuplicateStrategy.UPDATE, commit=True))
    [customer] = store.customers.values()
    assert customer.created_at == datetime(2018, 2, 1, tzinfo=UTC)
    # Without the column the date stays.
    handlers.run(
        customers_request(
            content=lines("Nachname;PLZ Ort", "Muster;3000 Bern"),
            duplicates=DuplicateStrategy.UPDATE,
            commit=True,
        )
    )
    assert next(iter(store.customers.values())).created_at == datetime(2018, 2, 1, tzinfo=UTC)


def test_a_customer_since_date_in_the_future_is_refused(handlers: ImportHandlers) -> None:
    content = lines("Nachname;PLZ Ort;Kunde seit", "Muster;3000 Bern;01.01.2099")
    [outcome] = handlers.run(customers_request(content=content)).outcomes
    assert outcome.status is RowStatus.ERROR
    assert outcome.problem is not None
    assert (outcome.problem.field, outcome.problem.message) == (
        "customer_since",
        "the date lies in the future",
    )


def test_the_demo_takes_small_imports_only(store: Store, clock: FixedClock) -> None:
    store.company = factories.company()
    demo = ImportHandlers(
        uow=lambda: InMemoryUnitOfWork(store),
        clock=clock,
        reader=SemicolonReader(),
        limits=ImportLimits(max_bytes=2048, max_rows=2),
    )
    assert demo.run(customers_request(content=lines("Nachname", "A", "B"))).outcomes
    with raises_exactly(ValidationError, "imports in the demo may have at most 2 rows") as rows:
        demo.run(customers_request(content=lines("Nachname", "A", "B", "C")))
    assert (rows.value.field, rows.value.code) == ("file", "demo_import_too_many_rows")
    big = lines("Nachname", "x" * 2048)
    with raises_exactly(ValidationError, "files in the demo may have at most 2 KB") as size:
        demo.run(customers_request(content=big))
    assert (size.value.field, size.value.code) == ("file", "demo_import_too_large")
    assert ImportLimits(max_bytes=200 * 1024, max_rows=200) == DEMO_IMPORT_LIMITS


ARTICLES = lines(
    "Art.-Nr.;Bezeichnung;Langtext;Einheit;VK;MwSt;Gruppe",
    "0021;Dienstleistung;Beratung IT;Std.;120,00;8.1;Beratung",
    ";Support;;;50.-;;",
    "0030;Kaputt;;Fass;10;;",
    "0031;Kaputt;;;zehn;;",
    "0032;Kaputt;;;10;5;",
)


def articles_request(**overrides: object) -> ImportRequest:
    values: dict[str, object] = {"target": ImportTarget.ARTICLES, "content": ARTICLES}
    values.update(overrides)
    return ImportRequest(**values)  # type: ignore[arg-type]  # test builder


def test_articles_are_imported(handlers: ImportHandlers, store: Store) -> None:
    run = handlers.run(articles_request(commit=True))
    assert [(o.status, o.number, o.name, o.detail) for o in run.outcomes] == [
        (RowStatus.NEW, "0021", "Dienstleistung", "CHF 120.00"),
        (RowStatus.NEW, "1", "Support", "CHF 50"),
        (RowStatus.ERROR, "0030", "Kaputt", ""),
        (RowStatus.ERROR, "0031", "Kaputt", ""),
        (RowStatus.ERROR, "0032", "Kaputt", ""),
    ]
    assert [o.problem.field for o in run.outcomes[2:] if o.problem is not None] == [
        "unit",
        "price",
        "tax_category",
    ]
    saved = {article.number: article for article in store.articles.values()}
    service = saved["0021"]
    assert (service.unit.code, service.tax_category) == ("HUR", TaxCategory.STANDARD)
    assert (service.description, service.group) == ("Beratung IT", "Beratung")
    assert service.prices == {Currency.CHF: Decimal("120.00")}
    assert saved["1"].unit.code == "C62"


def test_article_prices_per_currency(handlers: ImportHandlers, store: Store) -> None:
    content = lines("Bezeichnung;Preis CHF;Preis EUR", "Beratung;130;120")
    handlers.run(articles_request(content=content, commit=True))
    [article] = store.articles.values()
    assert article.prices == {Currency.CHF: Decimal(130), Currency.EUR: Decimal(120)}
    assert article.unit.code == "C62"


def test_article_duplicates_by_number_or_name(handlers: ImportHandlers, store: Store) -> None:
    by_number = factories.article(number="0021", name="Alt")
    by_name = factories.article(
        number="9", name="support", prices={Currency.EUR: Decimal(45)}, description="Bleibt"
    )
    store.articles.update({by_number.id: by_number, by_name.id: by_name})
    run = handlers.run(articles_request())
    assert [(o.status, o.number) for o in run.outcomes[:2]] == [
        (RowStatus.SKIPPED, "0021"),
        (RowStatus.SKIPPED, "9"),
    ]
    run = handlers.run(articles_request(duplicates=DuplicateStrategy.UPDATE, commit=True))
    assert [o.status for o in run.outcomes[:2]] == [RowStatus.UPDATED, RowStatus.UPDATED]
    updated = store.articles[by_name.id]
    # A price in the company's currency is added, the euro price and the text stay.
    assert updated.prices == {Currency.EUR: Decimal(45), Currency.CHF: Decimal(50)}
    assert (updated.name, updated.description, updated.number) == ("Support", "Bleibt", "9")
    assert store.articles[by_number.id].name == "Dienstleistung"
    assert len(store.articles) == 2


def test_article_duplicates_created_anew(handlers: ImportHandlers, store: Store) -> None:
    existing = factories.article(number="0021")
    store.articles[existing.id] = existing
    run = handlers.run(articles_request(duplicates=DuplicateStrategy.CREATE, commit=True))
    assert [(o.status, o.number) for o in run.outcomes[:2]] == [
        (RowStatus.NEW, "1"),
        (RowStatus.NEW, "2"),
    ]


def test_articles_need_a_name_column(handlers: ImportHandlers) -> None:
    content = lines("Preis", "10")
    assert handlers.run(articles_request(content=content)).missing == (("number", "name"),)
    with raises_exactly(ValidationError, "missing columns: number or name") as caught:
        handlers.run(articles_request(content=content, commit=True))
    assert caught.value.code == "mapping_incomplete"


def test_rows_without_a_name_are_errors(handlers: ImportHandlers) -> None:
    run = handlers.run(articles_request(content=lines("Bezeichnung;Preis", ";10")))
    problem = run.outcomes[0].problem
    assert problem is not None
    assert (problem.field, run.outcomes[0].name) == ("name", "")


def test_templates_are_saved_listed_and_deleted(handlers: ImportHandlers, store: Store) -> None:
    template = handlers.save_template(
        SaveTemplate(
            target=ImportTarget.CUSTOMERS,
            name="  Altes Programm ",
            columns={"number": "KdNr", "company_name": "Firma", "note": " "},
        )
    )
    assert (template.name, dict(template.columns)) == (
        "Altes Programm",
        {"number": "KdNr", "company_name": "Firma"},
    )
    assert template.created_at == NOW
    assert handlers.templates(ImportTarget.CUSTOMERS) == [template]
    assert handlers.templates(ImportTarget.ARTICLES) == []
    with raises_exactly(ConflictError, "a template named altes programm exists already") as caught:
        handlers.save_template(
            SaveTemplate(
                target=ImportTarget.CUSTOMERS, name="altes programm", columns={"city": "Ort"}
            )
        )
    assert "name" in caught.value.details
    handlers.delete_template(template.id)
    assert store.import_templates == {}
    with raises_exactly(NotFoundError, "import template not found"):
        handlers.delete_template(template.id)


@pytest.mark.parametrize(
    ("columns", "code", "message"),
    [
        ({"shoe_size": "Schuhe"}, "unknown_field", "unknown fields: shoe_size"),
        ({"city": "  "}, "empty_template", "the template maps no column"),
        ({}, "empty_template", "the template maps no column"),
    ],
)
def test_invalid_templates_are_rejected(
    handlers: ImportHandlers, columns: dict[str, str], code: str, message: str
) -> None:
    with raises_exactly(ValidationError, message) as caught:
        handlers.save_template(
            SaveTemplate(target=ImportTarget.CUSTOMERS, name="X", columns=columns)
        )
    assert (caught.value.field, caught.value.code) == ("columns", code)


def test_templates_need_a_name(handlers: ImportHandlers) -> None:
    with pytest.raises(ValidationError) as caught:
        handlers.save_template(
            SaveTemplate(target=ImportTarget.ARTICLES, name=" ", columns={"name": "Bezeichnung"})
        )
    assert caught.value.field == "name"


def test_updating_keeps_the_country_when_the_file_names_none(
    handlers: ImportHandlers, store: Store
) -> None:
    existing = factories.customer(
        number="7",
        company_name="Berlin GmbH",
        address=factories.address(postal_code="10115", city="Berlin", country=CountryCode("DE")),
    )
    store.customers[existing.id] = existing
    content = lines("Nr;Firma;PLZ Ort", "7;Berlin GmbH;10117 Berlin")
    handlers.run(
        customers_request(content=content, duplicates=DuplicateStrategy.UPDATE, commit=True)
    )
    address = store.customers[existing.id].address
    assert (address.postal_code, address.country.value) == ("10117", "DE")


def test_street_and_house_number_change_together(handlers: ImportHandlers, store: Store) -> None:
    existing = factories.customer(
        number="7",
        company_name="Muster AG",
        address=factories.address(street="Alte Gasse", house_number="5"),
    )
    store.customers[existing.id] = existing
    content = lines("Nr;Strasse;Nachname", "7;Neue Strasse;Muster")
    handlers.run(
        customers_request(content=content, duplicates=DuplicateStrategy.UPDATE, commit=True)
    )
    updated = store.customers[existing.id]
    assert (updated.address.street, updated.address.house_number) == ("Neue Strasse", "")
    # A contact's last name does not turn a company into a person.
    assert (updated.kind, updated.company_name) == (CustomerKind.COMPANY, "Muster AG")


def test_unknown_country_prefixes_and_east_german_postal_codes(
    handlers: ImportHandlers, store: Store
) -> None:
    content = lines(
        "Firma;PLZ_Ort",
        "Bozen Srl;I-39100 Bozen",
        "Unklar AG;XY-1234 Nirgendwo",
        "Dresden GmbH;D-1067 Dresden",
    )
    run = handlers.run(customers_request(content=content, commit=True))
    problem = run.outcomes[1].problem
    assert problem is not None
    assert (problem.field, problem.code, problem.value) == (
        "postal_city",
        "unknown_country_prefix",
        "XY-1234 Nirgendwo",
    )
    places = {
        c.company_name: (c.address.postal_code, c.address.country.value)
        for c in store.customers.values()
    }
    # Spreadsheets drop the leading zero of postal codes like 01067.
    assert places == {"Bozen Srl": ("39100", "IT"), "Dresden GmbH": ("01067", "DE")}


def test_rows_with_errors_use_up_no_number(handlers: ImportHandlers) -> None:
    content = lines("Bezeichnung;Einheit", "Kaputt;Fass", "Beratung;Std.")
    run = handlers.run(articles_request(content=content, commit=True))
    assert [(o.status, o.number) for o in run.outcomes] == [
        (RowStatus.ERROR, ""),
        (RowStatus.NEW, "1"),
    ]
    customers = lines("Firma;PLZ;Ort", ";3000;Bern", "Muster AG;3000;Bern")
    run = handlers.run(customers_request(content=customers, commit=True))
    assert [o.number for o in run.outcomes] == ["", "1001"]


def test_price_problems_name_the_column_of_the_price(handlers: ImportHandlers) -> None:
    content = lines("Bezeichnung;Preis;Preis EUR", "A;-50;", "B;;1.00001")
    run = handlers.run(articles_request(content=content))
    problems = [o.problem for o in run.outcomes]
    assert [(p.field, p.code, p.value) for p in problems if p is not None] == [
        ("price", "invalid", "-50"),
        ("price_eur", "invalid", "1.00001"),
    ]


def test_amounts_follow_the_company_country(handlers: ImportHandlers, store: Store) -> None:
    content = lines("Bezeichnung;Preis", "Beratung;Fr. 1'250.-", "Stunde;1.500")
    handlers.run(articles_request(content=content, commit=True))
    prices = {a.name: a.prices for a in store.articles.values()}
    # In Switzerland "1.500" is one and a half.
    assert prices == {
        "Beratung": {Currency.CHF: Decimal(1250)},
        "Stunde": {Currency.CHF: Decimal("1.500")},
    }
    store.articles.clear()
    store.company = factories.company(
        address=factories.address(postal_code="10115", city="Berlin", country=CountryCode("DE")),
        default_currency=Currency.EUR,
    )
    handlers.run(articles_request(content=lines("Bezeichnung;Preis", "Stunde;1.500"), commit=True))
    [article] = store.articles.values()
    assert article.prices == {Currency.EUR: Decimal(1500)}
