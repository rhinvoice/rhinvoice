"""The SQL repositories, exercised through the real use cases."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

from rhinvoice.application.catalog.handlers import ArticleHandlers, SaveArticle
from rhinvoice.application.catalog.ports import ArticleQuery, ArticleSort
from rhinvoice.application.common import AddressInput, PageRequest, SortDirection
from rhinvoice.application.company.handlers import CompanyHandlers, SaveBankAccount, SaveCompany
from rhinvoice.application.customer.handlers import CustomerHandlers, SaveCustomer
from rhinvoice.application.customer.ports import CustomerQuery, CustomerSort
from rhinvoice.application.numbering.handlers import (
    ConfigureSequence,
    NumberingHandlers,
    allocate_number,
)
from rhinvoice.domain.company.print_layout import (
    FooterAccounts,
    LogoPosition,
    LogoSize,
    PrintFont,
    PrintLayout,
    PrintTemplate,
)
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.numbering.sequence import SequenceKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from tests.unit.domain.factories import CH_IBAN, CH_QR_IBAN

CLOCK = FixedClock(datetime(2026, 3, 9, 9, 0, tzinfo=UTC))
ZURICH = AddressInput(
    street="Bahnhofstrasse", house_number="1", postal_code="8001", city="Zürich", country="CH"
)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 32


def factory(engine: Engine) -> Callable[[], SqlUnitOfWork]:
    return lambda: SqlUnitOfWork(engine)


def test_company_and_logo(engine: Engine) -> None:
    handlers = CompanyHandlers(uow=factory(engine))
    assert handlers.get() is None
    created = handlers.save(
        SaveCompany(
            name="Muster GmbH",
            address=ZURICH,
            default_currency=Currency.CHF,
            default_language=Language.EN,
            email="info@muster.example",
            phone="+41 44 000 00 00",
            website="https://muster.ch",
            vat_number="CHE-123.456.788 MWST",
            tax_number="123/456",
            commercial_register="CH-020.4.000.000-0",
            small_business=True,
            cash_rounding=False,
            payment_terms_days=10,
            accent_hue=120,
        ),
    )
    assert handlers.get() == created
    updated = handlers.save(
        SaveCompany(name="Muster AG", address=ZURICH, default_currency=Currency.EUR)
    )
    assert updated.id == created.id
    assert handlers.get() == updated
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM company")).scalar_one() == 1

    assert handlers.get_logo() is None
    logo = handlers.set_logo(PNG)
    assert handlers.get_logo() == logo
    replaced = handlers.set_logo(PNG + b"\x02")
    assert handlers.get_logo() == replaced
    handlers.delete_logo()
    assert handlers.get_logo() is None


def test_only_one_company_row_is_possible(engine: Engine) -> None:
    CompanyHandlers(uow=factory(engine)).save(
        SaveCompany(name="Muster GmbH", address=ZURICH, default_currency=Currency.CHF),
    )
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO company (id, name, postal_code, city, country, default_currency,"
                " default_language, small_business, cash_rounding, payment_terms_days,"
                " accent_hue) VALUES (gen_random_uuid(), 'X', '1', 'X', 'CH', 'CHF', 'de',"
                " false, true, 30, 250)",
            ),
        )


def test_bank_accounts(engine: Engine) -> None:
    handlers = CompanyHandlers(uow=factory(engine))
    first = handlers.create_bank_account(
        SaveBankAccount(
            currency=Currency.CHF,
            bank_name="Musterbank",
            holder="Muster GmbH",
            iban=CH_IBAN,
            qr_iban=CH_QR_IBAN,
            bic="UBSWCHZH80A",
        ),
    )
    second = handlers.create_bank_account(
        SaveBankAccount(
            currency=Currency.CHF,
            bank_name="Zweitbank",
            holder="Muster",
            iban="CH5604835012345678009",
            is_default=True,
        ),
    )
    eur = handlers.create_bank_account(
        SaveBankAccount(
            currency=Currency.EUR, bank_name="Euro", holder="Muster", iban="LI21088100002324013AA"
        ),
    )
    accounts = handlers.list_bank_accounts()
    assert [a.id for a in accounts] == [second.id, first.id, eur.id]
    assert accounts[1].qr_iban is not None
    assert accounts[1].qr_iban.value == CH_QR_IBAN
    handlers.delete_bank_account(second.id)
    assert {a.id: a.is_default for a in handlers.list_bank_accounts()} == {
        first.id: True,
        eur.id: True,
    }


def test_the_database_enforces_one_default_per_currency(engine: Engine) -> None:
    handlers = CompanyHandlers(uow=factory(engine))
    handlers.create_bank_account(
        SaveBankAccount(currency=Currency.CHF, bank_name="A", holder="M", iban=CH_IBAN),
    )
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO bank_accounts (id, currency, bank_name, holder, iban, is_default)"
                " VALUES (gen_random_uuid(), 'CHF', 'B', 'M', 'CH5604835012345678009', true)",
            ),
        )


def test_customers(engine: Engine) -> None:
    handlers = CustomerHandlers(uow=factory(engine), clock=CLOCK)
    mueller = handlers.create(
        SaveCustomer(
            kind=CustomerKind.COMPANY,
            company_name="Müller & Söhne AG",
            contact_person="Frau Muster",
            address=ZURICH,
            email="info@mueller.example",
            vat_number="CHE-123.456.788",
            default_currency=Currency.EUR,
            default_language=Language.DE,
            tax_exempt=True,
            default_discount="2.5",
            payment_terms_days=20,
            delivery_address=AddressInput(
                postal_code="9490", city="Vaduz", country="LI", street="Städtle", house_number="1"
            ),
            note="Zeile 1\nZeile 2",
            group="Stammkunden",
        ),
    )
    person = handlers.create(
        SaveCustomer(
            kind=CustomerKind.PERSON,
            salutation="Herr",
            first_name="Max",
            last_name="Zürcher",
            address=AddressInput(postal_code="3000", city="Bern", country="CH"),
        ),
    )
    archived = handlers.create(
        SaveCustomer(kind=CustomerKind.COMPANY, company_name="100% Alt_AG", address=ZURICH),
    )
    handlers.archive(archived.id)

    assert handlers.get(mueller.id) == mueller
    assert handlers.get(person.id) == person
    assert handlers.get(mueller.id).default_discount == Decimal("2.50")

    assert [c.id for c in handlers.search(CustomerQuery(search="muller")).items] == [mueller.id]
    assert [c.id for c in handlers.search(CustomerQuery(search="ZURCHER")).items] == [person.id]
    assert [c.id for c in handlers.search(CustomerQuery(search="stammkunden")).items] == [
        mueller.id
    ]
    assert handlers.search(CustomerQuery(search="100%")).items == []
    assert [
        c.id for c in handlers.search(CustomerQuery(search="100%", include_archived=True)).items
    ] == [archived.id]
    assert handlers.search(CustomerQuery(search="t_A", include_archived=True)).total == 1
    assert handlers.search(CustomerQuery(search="%")).total == 0

    by_name = handlers.search(CustomerQuery(sort=CustomerSort.NAME, include_archived=True))
    # Natural (ICU) order: digits first, umlauts sort with their base letter.
    assert [c.id for c in by_name.items] == [archived.id, mueller.id, person.id]
    by_city = handlers.search(CustomerQuery(sort=CustomerSort.CITY, direction=SortDirection.DESC))
    assert [c.id for c in by_city.items] == [mueller.id, person.id]
    by_created = handlers.search(
        CustomerQuery(sort=CustomerSort.CREATED_AT, page=PageRequest(limit=1, offset=1))
    )
    assert by_created.total == 2
    assert len(by_created.items) == 1
    numbers = handlers.search(CustomerQuery(sort=CustomerSort.NUMBER, include_archived=True))
    assert [c.number for c in numbers.items] == ["1001", "1002", "1003"]

    renamed = handlers.update(
        person.id,
        SaveCustomer(
            kind=CustomerKind.PERSON,
            first_name="Max",
            last_name="Zürcher-Muster",
            address=AddressInput(postal_code="3000", city="Bern", country="CH"),
        ),
    )
    assert handlers.get(person.id) == renamed
    assert handlers.get(archived.id).archived is True

    apfel = handlers.create(
        SaveCustomer(kind=CustomerKind.COMPANY, company_name="Äpfel AG", address=ZURICH),
    )
    natural = handlers.search(
        CustomerQuery(sort=CustomerSort.NAME, search="AG", include_archived=True)
    )
    assert [c.id for c in natural.items] == [archived.id, apfel.id, mueller.id]


def test_articles(engine: Engine) -> None:
    handlers = ArticleHandlers(uow=factory(engine), clock=CLOCK)
    beratung = handlers.create(
        SaveArticle(
            name="Beratung",
            unit="HUR",
            tax_category=TaxCategory.STANDARD,
            prices={Currency.CHF: "150.1234", Currency.EUR: "160"},
            description="Stundenansatz",
            group="Dienstleistung",
        ),
    )
    kabel = handlers.create(
        SaveArticle(
            name="Kabel", group="Material", description="Netzwerkkabel", supply=Supply.GOODS
        )
    )
    old = handlers.create(SaveArticle(name="Übergrösse", prices={Currency.CHF: "1"}))
    handlers.archive(old.id)

    stored = handlers.get(beratung.id)
    assert stored == beratung
    assert stored.prices == {Currency.CHF: Decimal("150.1234"), Currency.EUR: Decimal(160)}
    assert handlers.get(kabel.id).prices == {}
    assert (handlers.get(kabel.id).supply, stored.supply) == (Supply.GOODS, Supply.SERVICE)

    updated = handlers.update(
        beratung.id, SaveArticle(name="Beratung", unit="HUR", prices={Currency.CHF: "170"})
    )
    assert handlers.get(beratung.id).prices == {Currency.CHF: Decimal(170)}
    assert updated.prices == {Currency.CHF: Decimal(170)}

    assert [a.id for a in handlers.search(ArticleQuery(search="netzwerk")).items] == [kabel.id]
    assert [
        a.id
        for a in handlers.search(ArticleQuery(search="ubergrosse", include_archived=True)).items
    ] == [old.id]
    page = handlers.search(ArticleQuery(sort=ArticleSort.GROUP, direction=SortDirection.DESC))
    assert [a.id for a in page.items] == [kabel.id, beratung.id]
    assert page.items[1].prices == {Currency.CHF: Decimal(170)}
    assert handlers.search(ArticleQuery(sort=ArticleSort.NAME, include_archived=True)).total == 3
    assert (
        handlers.search(ArticleQuery(sort=ArticleSort.CREATED_AT, search="nothing-matches")).items
        == []
    )


def test_number_sequences(engine: Engine) -> None:
    handlers = NumberingHandlers(uow=factory(engine), clock=CLOCK)
    view = handlers.configure(
        ConfigureSequence(
            kind=SequenceKind.INVOICE,
            pattern="R{YYYY}{NNNN}",
            start_value=1,
            yearly_reset=True,
            next_value=12,
        ),
    )
    assert view.next_number == "R20260012"
    with SqlUnitOfWork(engine) as uow:
        assert allocate_number(uow, SequenceKind.INVOICE, CLOCK.today()) == "R20260012"
        uow.commit()
    listed = {v.sequence.kind: v for v in handlers.list()}
    assert listed[SequenceKind.INVOICE].next_number == "R20260013"
    assert listed[SequenceKind.INVOICE].sequence.last_year == 2026
    assert listed[SequenceKind.QUOTE].next_number == "A20260001"


def test_sequence_rows_are_locked_while_allocating(engine: Engine) -> None:
    with SqlUnitOfWork(engine) as uow:
        allocate_number(uow, SequenceKind.INVOICE, CLOCK.today())
        uow.commit()
        assert uow.sequences.lock(SequenceKind.INVOICE).next_value == 2
        with engine.connect() as other:
            other.execute(text("SET lock_timeout = '200ms'"))
            with pytest.raises(OperationalError, match="lock timeout"):
                other.execute(
                    text("SELECT * FROM number_sequences WHERE kind = 'invoice' FOR UPDATE")
                )


def test_unknown_ids_return_nothing(engine: Engine) -> None:
    with SqlUnitOfWork(engine) as uow:
        assert uow.customers.get(new_id()) is None
        assert uow.articles.get(new_id()) is None
        assert uow.bank_accounts.get(new_id()) is None
        assert not uow.customers.number_exists("1")
        assert not uow.articles.number_exists("1", exclude_id=new_id())


def test_the_first_number_is_serialised_on_an_empty_table(engine: Engine) -> None:
    """Two first allocations must not both get number 1 (review finding)."""
    with SqlUnitOfWork(engine) as first:
        assert allocate_number(first, SequenceKind.QUOTE, CLOCK.today()) == "A20260001"
        # The uncommitted row is invisible to others, but a concurrent first allocation
        # runs the same INSERT ... ON CONFLICT and has to wait for this transaction.
        with SqlUnitOfWork(engine) as second:
            # The test needs the unit of work's own connection to set a short timeout.
            connection = second.sequences._connection  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            connection.execute(text("SET lock_timeout = '200ms'"))
            with pytest.raises(OperationalError, match="lock timeout"):
                allocate_number(second, SequenceKind.QUOTE, CLOCK.today())
        first.commit()
    with SqlUnitOfWork(engine) as second:
        assert allocate_number(second, SequenceKind.QUOTE, CLOCK.today()) == "A20260002"


def test_customers_are_found_with_umlaut_spellings_and_sorted_naturally(engine: Engine) -> None:
    handlers = CustomerHandlers(uow=factory(engine), clock=CLOCK)
    mueller = handlers.create(
        SaveCustomer(
            kind=CustomerKind.COMPANY, company_name="Müller AG", address=ZURICH, number="9"
        ),
    )
    other = handlers.create(
        SaveCustomer(
            kind=CustomerKind.COMPANY, company_name="Andere AG", address=ZURICH, number="10"
        ),
    )
    assert [c.id for c in handlers.search(CustomerQuery(search="Mueller")).items] == [mueller.id]
    assert [c.id for c in handlers.search(CustomerQuery(search="MULLER")).items] == [mueller.id]
    by_number = handlers.search(CustomerQuery(sort=CustomerSort.NUMBER))
    assert [c.id for c in by_number.items] == [mueller.id, other.id]


def test_print_layout(engine: Engine) -> None:
    handlers = CompanyHandlers(uow=factory(engine))
    assert handlers.print_layout() == PrintLayout()
    layout = PrintLayout(
        template=PrintTemplate.CLASSIC,
        logo_position=LogoPosition.LEFT,
        logo_size=LogoSize.SMALL,
        font=PrintFont.SERIF,
        sender_line=False,
        contact=True,
        position_numbers=False,
        footer_accounts=FooterAccounts.ALL,
        e_invoice=False,
    )
    handlers.save_print_layout(layout)
    assert handlers.print_layout() == layout
    handlers.save_print_layout(PrintLayout())
    assert handlers.print_layout() == PrintLayout()
