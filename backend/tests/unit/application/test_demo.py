"""Demo data for a test installation."""

import io
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import pairwise

import pytest
from pypdf import PdfReader

from rhinvoice.application.catalog.handlers import ArticleHandlers
from rhinvoice.application.company.handlers import CompanyHandlers
from rhinvoice.application.customer.handlers import CustomerHandlers
from rhinvoice.application.demo.handlers import (
    ACCOUNT_SETS,
    ARTICLES,
    CUSTOMERS,
    DEMO_ACCOUNTS,
    DEMO_COMPANIES,
    DEMO_EMAIL,
    DEMO_PASSWORD,
    HOME_PLACES,
    DemoHandlers,
    DemoResult,
    customers_for,
)
from rhinvoice.application.document.dashboard import DashboardHandlers
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput
from rhinvoice.application.errors import ConflictError
from rhinvoice.application.identity.handlers import IdentityHandlers, Login
from rhinvoice.application.importing.handlers import ImportHandlers
from rhinvoice.domain.company.company import Company
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.document.document import (
    DisplayStatus,
    Document,
    DocumentStatus,
    DocumentType,
)
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.tax.vat_number import VatNumber
from rhinvoice.infrastructure.importing.reader import SpreadsheetReader
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import (
    FakePasswordHasher,
    FakeTotpService,
    InMemoryUnitOfWork,
    Store,
)
from tests.unit.domain import factories

TODAY = NOW.date()


@pytest.fixture
def demo(store: Store, clock: FixedClock) -> DemoHandlers:
    def uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    return DemoHandlers(
        uow=uow,
        clock=clock,
        identity=IdentityHandlers(
            uow=uow, hasher=FakePasswordHasher(), totp=FakeTotpService(), clock=clock
        ),
        company=CompanyHandlers(uow=uow),
        customers=CustomerHandlers(uow=uow, clock=clock),
        articles=ArticleHandlers(uow=uow, clock=clock),
        documents=DocumentHandlers(uow=uow, clock=clock),
        imports=ImportHandlers(uow=uow, clock=clock, reader=SpreadsheetReader()),
    )


def german(**overrides: object) -> Company:
    values: dict[str, object] = {
        "address": factories.address(country=CountryCode("DE"), postal_code="10115", city="Berlin"),
        "default_currency": Currency.EUR,
        "vat_number": VatNumber.parse("DE123456789"),
    }
    values.update(overrides)
    return factories.company(**values)


def austrian(**overrides: object) -> Company:
    values: dict[str, object] = {
        "address": factories.address(country=CountryCode("AT"), postal_code="1010", city="Wien"),
        "default_currency": Currency.EUR,
        "vat_number": VatNumber.parse("ATU12345675"),
    }
    values.update(overrides)
    return factories.company(**values)


def documents_of(store: Store) -> list[Document]:
    """Collect the documents the demo wrote, not the old invoices it took over."""
    return [
        stored.document for stored in store.documents.values() if not stored.document.is_imported
    ]


def test_the_demo_takes_over_invoices_of_the_program_used_before(
    demo: DemoHandlers, store: Store
) -> None:
    store.company = factories.company(name="Pixelwerk GmbH")
    result = demo.seed()
    assert result.imported == 3
    imported = sorted(
        (stored.document for stored in store.documents.values() if stored.document.is_imported),
        key=lambda document: document.number or "",
    )
    assert [document.number for document in imported] == [
        "RE-2023-117",
        "RE-2023-142",
        "RE-2023-163",
    ]
    assert all(document.status is DocumentStatus.PAID for document in imported)
    assert all(store.pdfs[document.id].startswith(b"%PDF-1.4") for document in imported)
    assert b"(MWST 7.7 %: CHF 184.80) Tj" in store.pdfs[imported[0].id]
    totals = imported[0].issued_totals
    assert totals is not None
    assert str(totals.total.amount) == "2584.80"
    [(attachment, _)] = store.attachments.values()
    assert attachment.file_name == "Rechnungen 2023/Zahlungserinnerung RE-2023-117.pdf"
    # A plain one-page PDF that tools can read, its text as written.
    text = PdfReader(io.BytesIO(store.pdfs[imported[0].id])).pages[0].extract_text()
    assert "Rechnung RE-2023-117" in text
    assert "Total CHF 2584.80" in text
    assert (
        "(geschlossen)" in PdfReader(io.BytesIO(store.pdfs[imported[1].id])).pages[0].extract_text()
    )
    former = next(c for c in store.customers.values() if c.company_name.startswith("Pension"))
    assert former.archived
    assert former.address.city == store.company.address.city


def test_a_swiss_installation_gets_invoices_since_january_of_last_year(
    demo: DemoHandlers, store: Store
) -> None:
    store.company = factories.company(name="Pixelwerk GmbH")
    result = demo.seed()
    assert (result.customers, result.articles, result.bank_accounts, result.quotes) == (
        len(CUSTOMERS),
        len(ARTICLES),
        2,
        4,
    )
    accounts = sorted(store.bank_accounts.values(), key=lambda account: account.currency.value)
    assert [(account.currency, account.iban.value, account.holder) for account in accounts] == [
        (Currency.CHF, "CH9300762011623852957", "Pixelwerk GmbH"),
        (Currency.EUR, "CH5604835012345678009", "Pixelwerk GmbH"),
    ]
    assert all(account.is_default for account in accounts)
    documents = documents_of(store)
    invoices = [document for document in documents if document.type is DocumentType.INVOICE]
    issued = [document for document in invoices if not document.is_draft]
    assert len(issued) == result.invoices
    dates = sorted(issue for document in issued if (issue := document.content.issue_date))
    # Every nine days from early January of last year up to today.
    assert date(2025, 1, 5) <= dates[0] < date(2025, 1, 14)
    assert dates[-1] == TODAY
    assert {(later - earlier).days for earlier, later in pairwise(dates)} == {9}
    statuses = Counter(document.display_status(TODAY) for document in invoices)
    assert statuses[DisplayStatus.DRAFT] == 1
    assert statuses[DisplayStatus.CANCELLED] == 1
    # Three unpaid and one partly paid invoice past their due date, for the dunning.
    assert statuses[DisplayStatus.OVERDUE] == 4
    assert [document.status for document in invoices].count(DocumentStatus.PARTIALLY_PAID) == 1
    assert statuses[DisplayStatus.PAID] > len(issued) // 2
    # The newest invoice is the cancelled one: its month keeps its revenue.
    [cancelled] = [document for document in invoices if document.status is DocumentStatus.CANCELLED]
    assert cancelled.content.issue_date == TODAY
    treatments = {document.content.treatment for document in issued}
    assert treatments >= {TaxTreatment.DOMESTIC, TaxTreatment.REVERSE_CHARGE, TaxTreatment.EXPORT}
    # The book is goods: abroad it leaves Switzerland as an export delivery.
    goods = {
        treatment for document in issued for treatment in document.content.treatments
    } - treatments
    assert goods == {TaxTreatment.GOODS_EXPORT}
    assert {document.content.currency for document in issued} == {Currency.CHF, Currency.EUR}
    quotes = Counter(
        document.status for document in documents if document.type is DocumentType.QUOTE
    )
    assert quotes == {
        DocumentStatus.ACCEPTED: 1,
        DocumentStatus.DECLINED: 1,
        DocumentStatus.SENT: 2,
    }
    payments = [payment for document in issued for payment in document.payments]
    assert payments
    assert all(payment.paid_on <= TODAY for payment in payments)


def test_the_overview_has_an_example_of_every_age(
    demo: DemoHandlers, store: Store, clock: FixedClock
) -> None:
    store.company = factories.company()
    demo.seed()
    overview = DashboardHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock).overview()
    late = [
        sum((getattr(row, field).amount for row in overview.aging), Decimal(0))
        for field in ("not_due", "late_30", "late_60", "late_more")
    ]
    assert all(amount > 0 for amount in late)
    assert all(row.current.amount >= 0 for row in overview.year_to_date)
    assert overview.days_to_pay


@pytest.mark.parametrize(
    "today",
    [date(2026, 1, 3), date(2026, 3, 5), date(2026, 12, 31), date(2024, 2, 29)],
)
def test_any_day_of_the_year(
    demo: DemoHandlers, store: Store, clock: FixedClock, today: date
) -> None:
    clock.set(datetime(today.year, today.month, today.day, 10, tzinfo=UTC))
    store.company = factories.company()
    demo.seed()
    overview = DashboardHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock).overview()
    # No month of the overview loses revenue to the cancellation.
    assert all(month.net.amount >= 0 for month in overview.revenue)
    issued = [
        document.content.issue_date
        for document in documents_of(store)
        if document.type is DocumentType.INVOICE and not document.is_draft
    ]
    assert max(issue for issue in issued if issue is not None) == today
    assert min(issue for issue in issued if issue is not None) >= date(today.year - 1, 1, 5)


def test_a_german_installation_invoices_mostly_at_home(demo: DemoHandlers, store: Store) -> None:
    store.company = german()
    result = demo.seed()
    assert result.bank_accounts == 1
    [account] = store.bank_accounts.values()
    assert account.iban.value == "DE89370400440532013000"
    assert account.bic is not None
    assert account.bic.value == "COBADEFFXXX"
    issued = [
        document
        for document in documents_of(store)
        if document.type is DocumentType.INVOICE and not document.is_draft
    ]
    treatments = Counter(document.content.treatment for document in issued)
    assert treatments[TaxTreatment.DOMESTIC] > len(issued) // 2
    # Books to Austrian businesses are intra-Community supplies.
    goods = {treatment for document in issued for treatment in document.content.treatments}
    assert TaxTreatment.INTRA_COMMUNITY in goods
    assert {document.content.currency for document in issued} == {Currency.EUR}


def test_an_austrian_installation(demo: DemoHandlers, store: Store) -> None:
    store.company = austrian()
    result = demo.seed()
    assert result.bank_accounts == 1
    [account] = store.bank_accounts.values()
    assert account.iban.value == "AT611904300234573201"
    countries = Counter(customer.address.country.value for customer in store.customers.values())
    assert countries["AT"] >= len(CUSTOMERS) // 2


def test_the_customers_live_where_the_company_does() -> None:
    swiss = customers_for(Country.CH)
    assert swiss == CUSTOMERS
    assert customers_for(Country.LI) == CUSTOMERS
    home = customers_for(Country.DE)
    assert Counter(customer.address.country for customer in home)["DE"] == 7
    # Names and everything else stay.
    assert [customer.company_name for customer in home] == [
        customer.company_name for customer in CUSTOMERS
    ]


def test_an_incomplete_company_is_refused_before_anything_is_written(
    demo: DemoHandlers, store: Store
) -> None:
    store.company = austrian(vat_number=None)
    with raises_exactly(
        ConflictError,
        "complete the company details first: invoices above EUR 400 state the VAT ID (UID) of "
        "the company",
    ) as caught:
        demo.seed()
    assert caught.value.code == "demo_company_incomplete"
    assert (store.customers, store.articles, store.bank_accounts, store.documents) == (
        {},
        {},
        {},
        {},
    )


def test_missing_accounts_are_added_per_currency(demo: DemoHandlers, store: Store) -> None:
    store.company = factories.company()
    own = factories.bank_account(is_default=True)
    store.bank_accounts[own.id] = own
    result = demo.seed()
    assert result.bank_accounts == 1
    euro = [account for account in store.bank_accounts.values() if account.id != own.id]
    assert [(account.currency, account.is_default) for account in euro] == [(Currency.EUR, True)]
    assert store.bank_accounts[own.id] == own


def test_customers_and_articles_only(demo: DemoHandlers, store: Store) -> None:
    store.company = german()
    result = demo.seed(documents=False)
    assert result == DemoResult(len(CUSTOMERS), len(ARTICLES), 1, 0, 0)
    assert store.documents == {}


def test_only_into_a_new_installation(demo: DemoHandlers, store: Store) -> None:
    with raises_exactly(
        ConflictError, "set up the company first (the first-start wizard)"
    ) as caught:
        demo.seed()
    assert caught.value.code == "demo_needs_company"
    store.company = factories.company()
    customer = factories.customer()
    store.customers[customer.id] = customer
    with raises_exactly(
        ConflictError, "demo data only goes into an installation without customers and documents"
    ) as refused:
        demo.seed()
    assert refused.value.code == "demo_not_empty"
    # A document alone is enough to refuse.
    demo.documents.create(DocumentType.INVOICE, DraftInput(customer_id=customer.id))
    del store.customers[customer.id]
    with raises_exactly(
        ConflictError, "demo data only goes into an installation without customers and documents"
    ):
        demo.seed()


def test_every_company_country_has_demo_places_and_accounts() -> None:
    """A new country profile also brings demo addresses and an example bank account."""
    assert set(HOME_PLACES) == set(Country)
    assert set(ACCOUNT_SETS) == set(Country)
    for country in Country:
        assert ACCOUNT_SETS[country] in DEMO_ACCOUNTS
        area = profile_of(country).vat.area
        at_home = [c for c in customers_for(country) if c.address.country in area]
        # Most demo customers are domestic, a few are abroad for the other tax cases.
        assert len(at_home) > len(CUSTOMERS) / 2, country


@pytest.mark.parametrize("country", list(Country))
def test_a_public_demo_is_installed_per_country(
    demo: DemoHandlers, store: Store, country: Country
) -> None:
    result = demo.install(country)
    assert result.invoices > 0
    company = store.company
    assert company is not None
    assert company.country is country
    assert company.name == DEMO_COMPANIES[country].name
    [user] = store.users.values()
    assert (str(user.email), user.display_name) == (DEMO_EMAIL, "Demo")
    demo.identity.login(Login(email=DEMO_EMAIL, password=DEMO_PASSWORD))


def test_a_public_demo_is_only_installed_into_an_empty_installation(
    demo: DemoHandlers, store: Store
) -> None:
    demo.install(Country.CH)
    with raises_exactly(ConflictError, "setup has already been completed"):
        demo.install(Country.DE)
    assert store.company is not None
    assert store.company.country is Country.CH
