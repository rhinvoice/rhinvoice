"""Demo data for a test installation: customers, articles and a year of documents.

Only for an empty installation (no customers, no documents), so real data is
never mixed with invented records. Everything is made through the regular use
cases: numbers, tax cases and the history are the same as for real documents.
The names, addresses and numbers are invented; the IBANs are the official
examples of SIX and the ECBS.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.application.catalog.handlers import SaveArticle
from rhinvoice.application.common import AddressInput, PageRequest
from rhinvoice.application.company.handlers import SaveBankAccount, SaveCompany
from rhinvoice.application.customer.handlers import SaveCustomer
from rhinvoice.application.customer.ports import CustomerQuery
from rhinvoice.application.demo.old_invoices import old_invoices
from rhinvoice.application.document.handlers import DraftInput, LineInput, PaymentInput
from rhinvoice.application.document.ports import DocumentQuery
from rhinvoice.application.errors import ConflictError
from rhinvoice.application.identity.handlers import CreateUser
from rhinvoice.application.importing.fields import ImportTarget
from rhinvoice.application.importing.handlers import ImportRequest
from rhinvoice.application.importing.results import RowStatus
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.customer.customer import Customer, CustomerKind
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.application.catalog.handlers import ArticleHandlers
    from rhinvoice.application.company.handlers import CompanyHandlers
    from rhinvoice.application.customer.handlers import CustomerHandlers
    from rhinvoice.application.document.handlers import DocumentHandlers
    from rhinvoice.application.identity.handlers import IdentityHandlers
    from rhinvoice.application.importing.handlers import ImportHandlers
    from rhinvoice.application.uow import UnitOfWorkFactory
    from rhinvoice.domain.catalog.article import Article
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.shared.clock import Clock

DEMO_EMAIL = "demo@rhinvoice.com"
DEMO_PASSWORD = "rhinvoice-demo"  # noqa: S105 - public on purpose, shown on the login page
"""The login of a public demo installation; shown on its login page."""

DEMO_COMPANIES: dict[Country, SaveCompany] = {
    Country.CH: SaveCompany(
        name="Muster Webdesign GmbH",
        address=AddressInput("9450", "Altstätten", "CH", "Marktgasse", "8"),
        default_currency=Currency.CHF,
        email="info@muster-webdesign.example",
        website="https://muster-webdesign.example",
        vat_number="CHE-123.456.788 MWST",
        commercial_register="CHE-123.456.788, Handelsregister St. Gallen",
        cash_rounding=True,
    ),
    Country.LI: SaveCompany(
        name="Muster Webdesign Anstalt",
        address=AddressInput("9490", "Vaduz", "LI", "Städtle", "12"),
        default_currency=Currency.CHF,
        email="info@muster-webdesign.example",
        website="https://muster-webdesign.example",
        vat_number="12345",
        commercial_register="FL-0002.123.456-7",
        cash_rounding=True,
    ),
    Country.DE: SaveCompany(
        name="Muster Webdesign GmbH",
        address=AddressInput("88131", "Lindau", "DE", "Maximilianstraße", "10"),
        default_currency=Currency.EUR,
        email="info@muster-webdesign.example",
        website="https://muster-webdesign.example",
        vat_number="DE123456789",
        tax_number="127/123/45678",
        commercial_register="Amtsgericht Kempten HRB 12345",
    ),
    Country.AT: SaveCompany(
        name="Muster Webdesign GmbH",
        address=AddressInput("6900", "Bregenz", "AT", "Kaiserstraße", "4"),
        default_currency=Currency.EUR,
        email="info@muster-webdesign.example",
        website="https://muster-webdesign.example",
        vat_number="ATU12345678",
        commercial_register="FN 123456a, Landesgericht Feldkirch",
    ),
}
"""The company of a public demo, per country; made-up names and numbers."""

_ONE = PageRequest(limit=1)
PROBE_TOTAL = Decimal(5000)
"""A typical demo invoice total for checking the company's invoice details."""
_ALL_TYPES = frozenset(DocumentType)

CUSTOMERS: tuple[SaveCustomer, ...] = (
    SaveCustomer(
        kind=CustomerKind.COMPANY,
        company_name="Schreinerei Holzwerk GmbH",
        contact_person="Herr Meier",
        email="info@holzwerk.example",
        address=AddressInput("9443", "Widnau", "CH", "Dorfstrasse", "1"),
    ),
    SaveCustomer(
        kind=CustomerKind.COMPANY,
        company_name="Garage Rheintal AG",
        email="buchhaltung@garage-rheintal.example",
        address=AddressInput("9434", "Au", "CH", "Industriestrasse", "12"),
    ),
    SaveCustomer(
        kind=CustomerKind.COMPANY,
        company_name="Café Rheinblick",
        address=AddressInput("9400", "Rorschach", "CH", "Seestrasse", "5"),
        payment_terms_days=20,
    ),
    SaveCustomer(
        kind=CustomerKind.COMPANY,
        company_name="Atelier Vaduz Anstalt",
        address=AddressInput("9490", "Vaduz", "LI", "Städtle", "20"),
    ),
    SaveCustomer(
        kind=CustomerKind.PERSON,
        salutation="Frau Dr.",
        first_name="Anna",
        last_name="Keller",
        address=AddressInput("9000", "St. Gallen", "CH", "Bahnhofstrasse", "8"),
    ),
    SaveCustomer(
        kind=CustomerKind.COMPANY,
        company_name="Bodensee Medien GmbH",
        email="rechnung@bodensee-medien.example",
        vat_number="DE123456789",
        default_currency=Currency.EUR,
        address=AddressInput("88131", "Lindau", "DE", "Hafenstraße", "3"),
    ),
    SaveCustomer(
        kind=CustomerKind.COMPANY,
        company_name="Hotel Alpenblick GmbH",
        vat_number="ATU12345675",
        default_currency=Currency.EUR,
        address=AddressInput("6900", "Bregenz", "AT", "Kornmarktplatz", "4"),
    ),
    SaveCustomer(
        kind=CustomerKind.PERSON,
        salutation="Herr",
        first_name="Max",
        last_name="Muster",
        address=AddressInput("8001", "Zürich", "CH", "Musterweg", "2"),
    ),
    SaveCustomer(
        kind=CustomerKind.COMPANY,
        company_name="Northwind Inc.",
        address=AddressInput("10001", "New York", "US", "Main Street", "100"),
    ),
)

HOME_PLACES: dict[Country, tuple[AddressInput, ...]] = {
    # Replace the addresses of the first five customers and of the private customer, so
    # most customers are domestic for every country of the company.
    Country.CH: (),
    Country.LI: (),
    Country.DE: (
        AddressInput("88131", "Lindau", "DE", "Bahnhofplatz", "1"),
        AddressInput("78462", "Konstanz", "DE", "Marktstätte", "6"),
        AddressInput("88045", "Friedrichshafen", "DE", "Seestraße", "14"),
        AddressInput("88239", "Wangen", "DE", "Herrenstraße", "9"),
        AddressInput("80331", "München", "DE", "Sendlinger Straße", "21"),
        AddressInput("10115", "Berlin", "DE", "Invalidenstraße", "40"),
    ),
    Country.AT: (
        AddressInput("6850", "Dornbirn", "AT", "Marktplatz", "3"),
        AddressInput("6800", "Feldkirch", "AT", "Schmiedgasse", "12"),
        AddressInput("6020", "Innsbruck", "AT", "Maria-Theresien-Straße", "18"),
        AddressInput("4020", "Linz", "AT", "Landstraße", "31"),
        AddressInput("8010", "Graz", "AT", "Herrengasse", "7"),
        AddressInput("1010", "Wien", "AT", "Kärntner Straße", "22"),
    ),
}
HOME_CUSTOMERS = (0, 1, 2, 3, 4, 7)


def customers_for(country: Country) -> tuple[SaveCustomer, ...]:
    """Place most demo customers in the company's country."""
    places = dict(zip(HOME_CUSTOMERS, HOME_PLACES[country], strict=False))
    return tuple(
        replace(customer, address=places[index]) if index in places else customer
        for index, customer in enumerate(CUSTOMERS)
    )


ARTICLES: tuple[SaveArticle, ...] = (
    SaveArticle(name="Beratung", unit="HUR", prices={Currency.CHF: "150", Currency.EUR: "140"}),
    SaveArticle(name="Webdesign", unit="HUR", prices={Currency.CHF: "130", Currency.EUR: "120"}),
    SaveArticle(name="Workshop", unit="DAY", prices={Currency.CHF: "1200", Currency.EUR: "1100"}),
    SaveArticle(name="Hosting", unit="MON", prices={Currency.CHF: "29", Currency.EUR: "27"}),
    SaveArticle(
        name="Wartungspauschale", unit="LS", prices={Currency.CHF: "450", Currency.EUR: "420"}
    ),
    SaveArticle(
        name="Fachbuch «Gutes Design»",
        unit="C62",
        tax_category=TaxCategory.REDUCED,
        prices={Currency.CHF: "38.50", Currency.EUR: "35"},
        supply=Supply.GOODS,
    ),
    SaveArticle(name="Fotografie", unit="HUR", prices={Currency.CHF: "140", Currency.EUR: "130"}),
    SaveArticle(name="Domain", unit="ANN", prices={Currency.CHF: "25", Currency.EUR: "23"}),
)

# Who gets the invoices, in order: a few regular customers bring most of the revenue.
INVOICE_CUSTOMERS = (0, 1, 2, 0, 3, 4, 0, 1, 5, 6, 0, 2, 1, 7, 0, 3, 1, 8, 0, 2, 5, 1, 6, 0)
# The positions of an invoice: (article, quantity), cycled.
INVOICE_LINES: tuple[tuple[tuple[int, str], ...], ...] = (
    ((0, "16"), (1, "24.5")),
    ((2, "2"), (5, "6")),
    ((3, "12"), (4, "1"), (7, "3")),
    ((6, "14"), (0, "6")),
    ((4, "1"), (1, "18"), (5, "2")),
    ((2, "1"), (0, "8"), (6, "4")),
)
INVOICE_EVERY_DAYS = 9
FIRST_INVOICE = (1, 5)
"""Month and day of last year where the invoices start: the overview compares whole years."""
PAYMENT_DELAYS = (12, 20, 25, 33, 9, 28)
"""Days after the issue date at which the customers paid, cycled."""
# Invoices counted back from the newest (0, issued today): left open past their due date,
# about 6, 42 and 78 days late, so every age of the overview has an example.
OVERDUE_BACK = frozenset({4, 8, 12})
PARTLY_PAID_BACK = 5
CANCELLED_BACK = 0
"""The newest invoice is cancelled the day it was issued: its month keeps its revenue."""
QUOTES_DAYS_AGO = (40, 25, 12, 3)
DEMO_ACCOUNTS: dict[str, tuple[SaveBankAccount, ...]] = {
    # Official examples of SIX (Swiss IBAN, QR-IBAN) and the ECBS.
    "swiss": (
        SaveBankAccount(
            currency=Currency.CHF,
            bank_name="Demo-Bank",
            holder="",
            iban="CH9300762011623852957",
            qr_iban="CH4431999123000889012",
            is_default=True,
        ),
        SaveBankAccount(
            currency=Currency.EUR,
            bank_name="Demo-Bank",
            holder="",
            iban="CH5604835012345678009",
            is_default=True,
        ),
    ),
    "german": (
        SaveBankAccount(
            currency=Currency.EUR,
            bank_name="Demo-Bank",
            holder="",
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
            is_default=True,
        ),
    ),
    "austrian": (
        SaveBankAccount(
            currency=Currency.EUR,
            bank_name="Demo-Bank",
            holder="",
            iban="AT611904300234573201",
            bic="BKAUATWWXXX",
            is_default=True,
        ),
    ),
}
ACCOUNT_SETS = {
    Country.CH: "swiss",
    Country.LI: "swiss",
    Country.DE: "german",
    Country.AT: "austrian",
}


@dataclass(frozen=True, slots=True)
class DemoResult:
    customers: int
    articles: int
    bank_accounts: int
    invoices: int
    quotes: int
    imported: int = 0
    """Invoices of a program used before, taken over with their PDF."""


@dataclass(frozen=True, slots=True)
class DemoHandlers:
    uow: UnitOfWorkFactory
    clock: Clock
    identity: IdentityHandlers
    company: CompanyHandlers
    customers: CustomerHandlers
    articles: ArticleHandlers
    documents: DocumentHandlers
    imports: ImportHandlers

    def install(self, country: Country) -> DemoResult:
        """Set up an empty installation as a public demo of ``country``.

        Creates the demo login, the demo company and its data. Refused once a user
        exists, so it never touches an installation that is in use.
        """
        self.identity.create_first_user(
            CreateUser(email=DEMO_EMAIL, display_name="Demo", password=DEMO_PASSWORD)
        )
        self.company.save(DEMO_COMPANIES[country])
        return self.seed()

    def seed(self, *, documents: bool = True) -> DemoResult:
        """Fill an empty installation; with ``documents`` also invoices and quotes.

        Everything is checked first: a failure half way would leave data behind,
        and a second run then refuses the installation as not empty.
        """
        company = self.company.get()
        if company is None:
            raise ConflictError(
                "set up the company first (the first-start wizard)", code="demo_needs_company"
            )
        self._require_empty()
        self._require_invoice_details(company)
        commands = customers_for(company.country)
        accounts = self._add_missing_accounts(company, commands)
        customers = [self.customers.create(command) for command in commands]
        articles = [self.articles.create(command) for command in ARTICLES]
        if not documents:
            return DemoResult(len(customers), len(articles), accounts, 0, 0)
        currency = company.default_currency
        invoices = self._invoices(customers, articles, currency)
        quotes = self._quotes(customers, articles, currency)
        imported = self._old_invoices(company, customers)
        return DemoResult(len(customers), len(articles), accounts, invoices, quotes, imported)

    def _old_invoices(self, company: Company, customers: list[Customer]) -> int:
        """Take over a few invoices of the program the demo company used before."""
        content, files = old_invoices(company, customers, self.clock.today())
        run = self.imports.run(
            ImportRequest(ImportTarget.INVOICES, content, files=files, commit=True)
        )
        return run.count(RowStatus.NEW)

    def _require_invoice_details(self, company: Company) -> None:
        """Refuse before writing when the company lacks what its invoices must state."""
        probe = Customer(
            id=new_id(),
            number="0",
            kind=CustomerKind.COMPANY,
            company_name="Demo",
            address=company.address,
            created_at=self.clock.now(),
        )
        try:
            profile_of(company.country).check_invoice(
                company, probe, Money(PROBE_TOTAL, company.default_currency)
            )
        except ValidationError as error:
            msg = f"complete the company details first: {error.message}"
            raise ConflictError(msg, code="demo_company_incomplete") from error

    def _add_missing_accounts(self, company: Company, customers: tuple[SaveCustomer, ...]) -> int:
        """Add the example account of every invoice currency that has no default account."""
        currencies = {company.default_currency} | {
            customer.default_currency
            for customer in customers
            if customer.default_currency is not None
        }
        defaults = {
            account.currency for account in self.company.list_bank_accounts() if account.is_default
        }
        added = 0
        for account in DEMO_ACCOUNTS[ACCOUNT_SETS[company.country]]:
            if account.currency in currencies and account.currency not in defaults:
                self.company.create_bank_account(replace(account, holder=company.name))
                defaults.add(account.currency)
                added += 1
        return added

    def _require_empty(self) -> None:
        today = self.clock.today()
        with self.uow() as uow:
            has_customers = uow.customers.search(CustomerQuery(page=_ONE)).total > 0
            has_documents = (
                uow.documents.search(DocumentQuery(today=today, types=_ALL_TYPES, page=_ONE)).total
                > 0
            )
        if has_customers or has_documents:
            raise ConflictError(
                "demo data only goes into an installation without customers and documents",
                code="demo_not_empty",
            )

    def _invoices(
        self, customers: list[Customer], articles: list[Article], currency: Currency
    ) -> int:
        today = self.clock.today()
        first = date(today.year - 1, *FIRST_INVOICE)
        count = (today - first).days // INVOICE_EVERY_DAYS + 1
        issued: list[UUID] = []
        for index in range(count):
            back = count - 1 - index
            issue_date = today - timedelta(days=back * INVOICE_EVERY_DAYS)
            invoice = self._issue(
                DocumentType.INVOICE,
                _draft(
                    customers[INVOICE_CUSTOMERS[index % len(INVOICE_CUSTOMERS)]],
                    articles,
                    INVOICE_LINES[index % len(INVOICE_LINES)],
                    issue_date,
                    currency,
                ),
            )
            issued.append(invoice)
            self._pay(invoice, index, back, issue_date, today)
        # A draft to finish, and the newest invoice cancelled.
        self.documents.create(
            DocumentType.INVOICE,
            _draft(customers[1], articles, INVOICE_LINES[0], None, currency),
        )
        self.documents.cancel(issued[-1 - CANCELLED_BACK])
        return len(issued)

    def _pay(self, invoice: UUID, index: int, back: int, issue_date: date, today: date) -> None:
        view = self.documents.get(invoice)
        due = view.document.content.due_date
        if back == CANCELLED_BACK or back in OVERDUE_BACK or due is None or due >= today:
            return
        if back == PARTLY_PAID_BACK:
            half = (view.totals.total.amount / 2).quantize(Decimal("0.01"))
            self.documents.add_payment(invoice, PaymentInput(paid_on=due, amount=str(half)))
            return
        delay = PAYMENT_DELAYS[index % len(PAYMENT_DELAYS)]
        self.documents.mark_paid(invoice, min(issue_date + timedelta(days=delay), today))

    def _quotes(
        self, customers: list[Customer], articles: list[Article], currency: Currency
    ) -> int:
        today = self.clock.today()
        quotes = [
            self._issue(
                DocumentType.QUOTE,
                _draft(
                    customers[index],
                    articles,
                    INVOICE_LINES[index % len(INVOICE_LINES)],
                    today - timedelta(days=days_ago),
                    currency,
                ),
            )
            for index, days_ago in enumerate(QUOTES_DAYS_AGO)
        ]
        self.documents.accept(quotes[0])
        self.documents.decline(quotes[1])
        return len(quotes)

    def _issue(self, document_type: DocumentType, draft: DraftInput) -> UUID:
        created = self.documents.create(document_type, draft).document.id
        return self.documents.issue(created).document.id


def _draft(
    customer: Customer,
    articles: list[Article],
    lines: tuple[tuple[int, str], ...],
    issue_date: date | None,
    currency: Currency,
) -> DraftInput:
    """Price the lines in the customer's currency, else the company's."""
    currency = customer.default_currency or currency
    return DraftInput(
        customer_id=customer.id,
        issue_date=issue_date,
        lines=tuple(
            LineInput(
                kind=LineKind.ITEM,
                description=articles[article].name,
                quantity=quantity,
                unit=articles[article].unit.code,
                unit_price=str(articles[article].prices[currency]),
                tax_category=articles[article].tax_category,
                supply=articles[article].supply,
                article_id=articles[article].id,
            )
            for article, quantity in lines
        ),
    )
