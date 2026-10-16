"""Sample invoices for every tax case, issued through the real handlers.

The unit tests check their e-invoices; `make einvoice-qa` writes them as files
(`python -m tests.einvoice_samples <folder> [<gotenberg url>]`) for the KoSIT
validator and Mustang, which judge them against EN 16931, XRechnung, ZUGFeRD
and PDF/A-3.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from rhinvoice.application.document.einvoice import EInvoiceProfile, problems
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.document.printing import PrintHandlers
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import DiscountKind, LineKind, PriceMode
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.iban import Bic, Iban
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.vat_number import VatNumber
from rhinvoice.infrastructure.einvoice.cii import CiiWriter
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer
from rhinvoice.infrastructure.rendering.pdf import ChromiumPdfRenderer, GotenbergPrinter
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

if TYPE_CHECKING:
    from rhinvoice.application.document.printing import PrintModel
    from rhinvoice.domain.company.bank_account import BankAccount
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.customer.customer import Customer

CUSTOMER = UUID(int=1)
ISSUED = date(2026, 3, 2)
DUE = date(2026, 4, 1)
# Official examples: SIX (CH, QR-IBAN), ECBS (DE, AT).
DE_IBAN = "DE89370400440532013000"
AT_IBAN = "AT611904300234573201"
EUR_BIC = "COBADEFFXXX"

CONSULTING = LineInput(
    kind=LineKind.ITEM,
    description="Beratung",
    details="Workshop vor Ort",
    quantity="12.5",
    unit="HUR",
    unit_price="150",
)
DISCOUNTED = LineInput(
    kind=LineKind.ITEM,
    description="Lizenz",
    quantity="3",
    unit="C62",
    unit_price="99.90",
    discount_percent="10",
)
REDUCED = LineInput(
    kind=LineKind.ITEM,
    description="Fachbuch",
    quantity="2",
    unit_price="38.50",
    tax_category=TaxCategory.REDUCED,
)
HEADING = LineInput(kind=LineKind.TEXT, description="Phase 1")
CREDIT_DISCOUNTED = LineInput(
    kind=LineKind.ITEM,
    description="Rücknahme Zubehör",
    quantity="-2",
    unit_price="33.33",
    discount_percent="15",
)
EXPORT_BOOK = LineInput(
    kind=LineKind.ITEM, description="Ausfuhr", unit_price="50", tax_category=TaxCategory.ZERO
)
EXEMPT = LineInput(
    kind=LineKind.ITEM, description="Schulung", unit_price="200", tax_category=TaxCategory.EXEMPT
)
PRINTER = LineInput(
    kind=LineKind.ITEM,
    description="Etikettendrucker",
    quantity="2",
    unit="C62",
    unit_price="450",
    discount_percent="5",
    supply=Supply.GOODS,
)
LABELS = LineInput(
    kind=LineKind.ITEM,
    description="Etiketten (Rolle)",
    quantity="20",
    unit_price="7.80",
    tax_category=TaxCategory.REDUCED,
    supply=Supply.GOODS,
)
CREDIT = LineInput(
    kind=LineKind.ITEM, description="Gutschrift Anzahlung", quantity="-1", unit_price="100"
)


@dataclass(frozen=True, slots=True)
class Sample:
    company: Company
    customer: Customer
    accounts: tuple[BankAccount, ...]
    draft: DraftInput
    cancel: bool = False


def _swiss() -> Company:
    return factories.company(
        name="Muster Werkstatt GmbH",
        email=EmailAddress("info@muster-werkstatt.example"),
        phone="+41 71 123 45 67",
        commercial_register="Handelsregister des Kantons Zürich",
    )


def _german(**overrides: object) -> Company:
    values: dict[str, object] = {
        "name": "Beispiel Software GmbH",
        "address": factories.address(
            street="Hauptstraße",
            house_number="7",
            postal_code="10115",
            city="Berlin",
            country=CountryCode("DE"),
        ),
        "default_currency": Currency.EUR,
        "vat_number": VatNumber.parse("DE123456789"),
        "tax_number": "27/123/45678",
        "commercial_register": "HRB 123456, Amtsgericht Berlin-Charlottenburg",
        "email": EmailAddress("rechnung@beispiel-software.example"),
        "phone": "+49 30 1234567",
    }
    values.update(overrides)
    return factories.company(**values)


def _chf_qr_account() -> BankAccount:
    return factories.bank_account(
        is_default=True, iban=Iban(factories.CH_IBAN), qr_iban=Iban(factories.CH_QR_IBAN)
    )


def _eur_account(iban: str, holder: str) -> BankAccount:
    return factories.bank_account(
        currency=Currency.EUR, iban=Iban(iban), bic=Bic(EUR_BIC), holder=holder, is_default=True
    )


def _draft(lines: tuple[LineInput, ...], **overrides: Any) -> DraftInput:  # noqa: ANN401 - test builder
    draft = DraftInput(
        customer_id=CUSTOMER,
        lines=lines,
        issue_date=ISSUED,
        due_date=DUE,
        subject="Projekt Beispiel",
    )
    return replace(draft, **overrides)


def samples() -> dict[str, Sample]:
    """One invoice per case of the tax and payment rules."""
    german_customer = factories.customer(
        id=CUSTOMER,
        kind=CustomerKind.PERSON,
        first_name="Erika",
        last_name="Mustermann",
        company_name="",
        address=factories.address(
            street="Heidestraße",
            house_number="17",
            postal_code="51147",
            city="Köln",
            country=CountryCode("DE"),
        ),
        email=EmailAddress("erika@example.com"),
    )
    swiss = _swiss()
    german = _german()
    berlin_account = _eur_account(DE_IBAN, german.name)
    return {
        # Two rates, a line and a document discount, the 5-centime rounding, a QR reference.
        "ch-domestic": Sample(
            swiss,
            factories.customer(id=CUSTOMER),
            (_chf_qr_account(),),
            _draft(
                (HEADING, CONSULTING, DISCOUNTED, REDUCED),
                discount_value="2.5",
                service_from=date(2026, 2, 1),
                service_to=date(2026, 2, 28),
                reference="PO-4711",
            ),
        ),
        "ch-domestic-cancellation": Sample(
            swiss,
            factories.customer(id=CUSTOMER),
            (_chf_qr_account(),),
            _draft((CONSULTING, DISCOUNTED)),
            cancel=True,
        ),
        # To a German business: it owes the VAT (reverse charge), paid in euros.
        "ch-reverse-charge": Sample(
            swiss,
            factories.customer(
                id=CUSTOMER,
                company_name="Kunde Deutschland GmbH",
                address=factories.address(
                    street="Marktplatz",
                    house_number="1",
                    postal_code="80331",
                    city="München",
                    country=CountryCode("DE"),
                ),
                vat_number=VatNumber.parse("DE987654321"),
            ),
            (_eur_account(DE_IBAN, swiss.name),),
            _draft((CONSULTING, DISCOUNTED), currency=Currency.EUR),
        ),
        # Outside Europe: an export without Swiss VAT.
        "ch-export": Sample(
            swiss,
            factories.customer(
                id=CUSTOMER,
                company_name="Customer Inc.",
                address=factories.address(
                    street="Main Street",
                    house_number="100",
                    postal_code="10001",
                    city="New York",
                    country=CountryCode("US"),
                ),
            ),
            (_eur_account(DE_IBAN, swiss.name),),
            _draft((CONSULTING,), currency=Currency.EUR),
        ),
        # Not registered for VAT at all: outside the scope of VAT.
        "ch-small-business": Sample(
            factories.company(
                name="Kleinbetrieb Muster",
                vat_number=VatNumber.parse("CHE-123.456.788"),
                small_business=True,
            ),
            factories.customer(id=CUSTOMER),
            (factories.bank_account(is_default=True),),
            _draft((CONSULTING,)),
        ),
        # Gross prices to a consumer, 19 % and 7 %, a discount as amount.
        "de-domestic-gross": Sample(
            german,
            german_customer,
            (berlin_account,),
            _draft(
                (CONSULTING, DISCOUNTED, REDUCED, CREDIT),
                price_mode=PriceMode.GROSS,
                discount_kind=DiscountKind.AMOUNT,
                discount_value="25",
                service_from=date(2026, 2, 27),
            ),
        ),
        "de-reverse-charge": Sample(
            german,
            factories.customer(
                id=CUSTOMER,
                company_name="Kunde Österreich GmbH",
                address=factories.address(
                    street="Ringstraße",
                    house_number="3",
                    postal_code="1010",
                    city="Wien",
                    country=CountryCode("AT"),
                ),
                vat_number=VatNumber.parse("ATU12345675"),
                email=EmailAddress("einkauf@kunde-oesterreich.example"),
            ),
            (berlin_account,),
            _draft((CONSULTING, REDUCED), reference="Bestellung 2026-17"),
        ),
        "de-small-business": Sample(
            _german(vat_number=None, small_business=True),
            german_customer,
            (berlin_account,),
            _draft((CONSULTING,)),
        ),
        # A German authority: XRechnung with the Leitweg-ID as buyer reference.
        "de-authority": Sample(
            german,
            replace(
                german_customer,
                kind=CustomerKind.COMPANY,
                company_name="Bezirksamt Beispiel",
                contact_person="Frau Beispiel",
            ),
            (berlin_account,),
            _draft((CONSULTING, DISCOUNTED), reference="04011000-12345-34"),
        ),
        # Gross prices in francs: net prices with four places, the 5-centime rounding.
        "ch-domestic-gross": Sample(
            swiss,
            factories.customer(id=CUSTOMER),
            (_chf_qr_account(),),
            _draft(
                (CONSULTING, DISCOUNTED, REDUCED, CREDIT, CREDIT_DISCOUNTED),
                price_mode=PriceMode.GROSS,
                discount_value="2.5",
            ),
        ),
        "ch-domestic-gross-cancellation": Sample(
            swiss,
            factories.customer(id=CUSTOMER),
            (_chf_qr_account(),),
            _draft((CONSULTING, DISCOUNTED, CREDIT_DISCOUNTED), price_mode=PriceMode.GROSS),
            cancel=True,
        ),
        # Taxed, zero-rated and exempt lines, a credit line with discount.
        "de-mixed": Sample(
            german,
            replace(german_customer, kind=CustomerKind.COMPANY, company_name="Kunde & Söhne <KG>"),
            (berlin_account,),
            _draft(
                (CONSULTING, EXPORT_BOOK, EXEMPT, CREDIT_DISCOUNTED),
                subject='Projekt "A & B" <2026>',
            ),
        ),
        "de-authority-cancellation": Sample(
            german,
            replace(
                german_customer,
                kind=CustomerKind.COMPANY,
                company_name="Bezirksamt Beispiel",
                contact_person="Frau Beispiel",
            ),
            (berlin_account,),
            _draft((CONSULTING, DISCOUNTED), reference="04011000-12345-34"),
            cancel=True,
        ),
        "li-domestic": Sample(
            factories.company(
                name="Muster Anstalt",
                address=factories.address(
                    street="Städtle",
                    house_number="1",
                    postal_code="9490",
                    city="Vaduz",
                    country=CountryCode("LI"),
                ),
                vat_number=VatNumber.parse("12345"),
                commercial_register="FL-0002.123.456-7",
            ),
            factories.customer(
                id=CUSTOMER,
                address=factories.address(
                    street="Landstrasse",
                    house_number="10",
                    postal_code="9495",
                    city="Triesen",
                    country=CountryCode("LI"),
                ),
            ),
            (_chf_qr_account(),),
            _draft((CONSULTING,)),
        ),
        # Goods and a service to an Austrian business: an intra-Community supply (K) with
        # the place of arrival, and reverse charge (AE) for the service.
        "de-intra-community": Sample(
            german,
            factories.customer(
                id=CUSTOMER,
                company_name="Kunde Österreich GmbH",
                address=factories.address(
                    street="Ringstraße",
                    house_number="3",
                    postal_code="1010",
                    city="Wien",
                    country=CountryCode("AT"),
                ),
                delivery_address=factories.address(
                    street="Industriestraße",
                    house_number="12",
                    postal_code="4020",
                    city="Linz",
                    country=CountryCode("AT"),
                ),
                vat_number=VatNumber.parse("ATU12345675"),
                email=EmailAddress("einkauf@kunde-oesterreich.example"),
            ),
            (berlin_account,),
            _draft((CONSULTING, PRINTER, LABELS), reference="Bestellung 2026-18"),
        ),
        # The same in Italian: the notices in the words of the VAT Directive.
        "de-intra-community-italian": Sample(
            german,
            factories.customer(
                id=CUSTOMER,
                company_name="Cliente Austria GmbH",
                address=factories.address(
                    street="Ringstraße",
                    house_number="3",
                    postal_code="1010",
                    city="Wien",
                    country=CountryCode("AT"),
                ),
                vat_number=VatNumber.parse("ATU12345675"),
                default_language=Language.IT,
            ),
            (berlin_account,),
            _draft((CONSULTING, PRINTER), language=Language.IT),
        ),
        "de-intra-community-cancellation": Sample(
            german,
            factories.customer(
                id=CUSTOMER,
                company_name="Kunde Österreich GmbH",
                address=factories.address(
                    street="Ringstraße",
                    house_number="3",
                    postal_code="1010",
                    city="Wien",
                    country=CountryCode("AT"),
                ),
                vat_number=VatNumber.parse("ATU12345675"),
                email=EmailAddress("einkauf@kunde-oesterreich.example"),
            ),
            (berlin_account,),
            _draft((PRINTER,), reference="Bestellung 2026-19"),
            cancel=True,
        ),
        # A private customer in Switzerland: the service is taxed in Austria, the goods
        # leave the EU as an export delivery (S and G on one invoice).
        "at-goods-export": Sample(
            factories.company(
                name="Muster OG",
                address=factories.address(
                    street="Herrengasse",
                    house_number="9",
                    postal_code="8010",
                    city="Graz",
                    country=CountryCode("AT"),
                ),
                default_currency=Currency.EUR,
                vat_number=VatNumber.parse("ATU12345675"),
            ),
            factories.customer(
                id=CUSTOMER,
                kind=CustomerKind.PERSON,
                first_name="Hans",
                last_name="Muster",
                company_name="",
            ),
            (_eur_account(AT_IBAN, "Muster OG"),),
            _draft((CONSULTING, PRINTER), currency=Currency.EUR),
        ),
        # From Switzerland to a German business: reverse charge for the service, the goods
        # are exported (the customer pays import VAT).
        "ch-goods-export": Sample(
            swiss,
            factories.customer(
                id=CUSTOMER,
                company_name="Kunde Deutschland GmbH",
                address=factories.address(
                    street="Marktplatz",
                    house_number="1",
                    postal_code="80331",
                    city="München",
                    country=CountryCode("DE"),
                ),
                vat_number=VatNumber.parse("DE987654321"),
            ),
            (_eur_account(DE_IBAN, swiss.name),),
            _draft((CONSULTING, PRINTER, LABELS), currency=Currency.EUR),
        ),
        # A French invoice to a customer outside Europe, in CHF with a QR reference.
        "ch-export-french": Sample(
            swiss,
            factories.customer(
                id=CUSTOMER,
                company_name="Client Canada Inc.",
                address=factories.address(
                    street="Rue Sainte-Catherine",
                    house_number="100",
                    postal_code="H2X 1Z4",
                    city="Montréal",
                    country=CountryCode("CA"),
                ),
                default_language=Language.FR,
            ),
            (_chf_qr_account(),),
            _draft((CONSULTING, PRINTER), language=Language.FR),
        ),
        "at-domestic": Sample(
            factories.company(
                name="Muster OG",
                address=factories.address(
                    street="Herrengasse",
                    house_number="9",
                    postal_code="8010",
                    city="Graz",
                    country=CountryCode("AT"),
                ),
                default_currency=Currency.EUR,
                vat_number=VatNumber.parse("ATU12345675"),
            ),
            factories.customer(
                id=CUSTOMER,
                address=factories.address(
                    street="Hauptplatz",
                    house_number="2",
                    postal_code="4020",
                    city="Linz",
                    country=CountryCode("AT"),
                ),
            ),
            (_eur_account(AT_IBAN, "Muster OG"),),
            _draft((CONSULTING, REDUCED)),
        ),
    }


def issue(sample: Sample) -> tuple[PrintHandlers, UUID]:
    """Issue the sample's invoice (and its cancellation); return the document to print."""
    store = Store()
    store.company = sample.company
    store.customers[CUSTOMER] = sample.customer
    for account in sample.accounts:
        store.bank_accounts[account.id] = account
    clock = FixedClock(NOW)

    def uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    documents = DocumentHandlers(uow=uow, clock=clock)
    invoice = documents.create(DocumentType.INVOICE, sample.draft).document.id
    documents.issue(invoice)
    printed = documents.cancel(invoice).document.cancellation_id if sample.cancel else invoice
    printing = PrintHandlers(
        uow=uow, clock=clock, documents=documents, renderer=JinjaDocumentRenderer()
    )
    return printing, printed


def model(sample: Sample) -> PrintModel:
    printing, document_id = issue(sample)
    return printing.model(printing.documents.get(document_id))


def write(folder: Path, gotenberg: str | None = None) -> None:
    """Write each sample's e-invoices that it is complete for, and with Gotenberg its PDF."""
    folder.mkdir(parents=True, exist_ok=True)
    writer = CiiWriter()
    html = JinjaDocumentRenderer()
    pdf = None if gotenberg is None else ChromiumPdfRenderer(html, GotenbergPrinter(gotenberg))
    for name, sample in samples().items():
        printed = model(sample)
        for profile in EInvoiceProfile:
            if not problems(printed, profile):
                (folder / f"{name}-{profile.value}.xml").write_bytes(writer.xml(printed, profile))
        if pdf is not None:
            embedded = (folder / f"{name}-{EInvoiceProfile.EN16931.value}.xml").read_bytes()
            (folder / f"{name}.pdf").write_bytes(pdf.pdf(printed, embedded))


if __name__ == "__main__":  # pragma: no cover - command line entry for `make einvoice-qa`
    write(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else None)
