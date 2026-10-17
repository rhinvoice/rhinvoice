# ruff: noqa: RUF001 - printed documents use typographic apostrophes, dashes and spaces.
"""The print template, rendered from documents of the in-memory application."""

from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest

from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.document.printing import PrintHandlers
from rhinvoice.domain.company.logo import Logo
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import DiscountKind, LineKind, PriceMode
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.iban import Bic
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.domain.tax.vat_number import VatNumber
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer, css_string
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)
HOURS = LineInput(
    kind=LineKind.ITEM,
    description="Beratung",
    details="Konzept & <Umsetzung>",
    quantity="12.5",
    unit="HUR",
    unit_price="1200",
    discount_percent="10",
)
FOOD = LineInput(
    kind=LineKind.ITEM,
    description="Kaffee",
    quantity="3",
    unit_price="12.35",
    tax_category=TaxCategory.REDUCED,
)
TITLE = LineInput(kind=LineKind.TEXT, description="Phase 2", details="ab März")
NBSP = " "


def printing_for(store: Store, theme_dir: Path | None = None) -> PrintHandlers:
    def uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    clock = FixedClock(NOW)
    return PrintHandlers(
        uow=uow,
        clock=clock,
        documents=DocumentHandlers(uow=uow, clock=clock),
        renderer=JinjaDocumentRenderer(theme_dir),
    )


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def printing(store: Store) -> PrintHandlers:
    store.company = factories.company(
        name="Muster & Co GmbH",
        email=EmailAddress.parse("info@muster.example"),
        phone="+41 44 000 00 00",
        website="muster.example",
        vat_number=VatNumber.parse("CHE-123.456.788 MWST"),
        tax_number="12/345",
        commercial_register="CH-020.4.000.000-0",
    )
    account = factories.bank_account(is_default=True, bic=Bic.parse("POFICHBEXXX"))
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(
        id=CUSTOMER, contact_person="Anna Muster", payment_terms_days=None
    )
    return printing_for(store)


def draft(**overrides: object) -> DraftInput:
    values: dict[str, object] = {"customer_id": CUSTOMER, "lines": (HOURS, TITLE, FOOD)}
    values.update(overrides)
    return DraftInput(**values)  # type: ignore[arg-type]  # test builder


def test_a_swiss_draft_invoice(printing: PrintHandlers) -> None:
    html = printing.preview_html(
        DocumentType.INVOICE,
        draft(
            subject="Website",
            reference="PO-7",
            service_from=date(2026, 2, 1),
            service_to=date(2026, 2, 28),
            discount_kind=DiscountKind.PERCENT,
            discount_value="5",
            intro_text="Guten Tag {kunde}",
            payment_text=(
                "Zahlbar bis {faellig}, Nr. {nummer}, {betrag} {waehrung} vom {datum}, {firma}"
            ),
            closing_text="Danke {unbekannt}",
        ),
    )
    assert html.startswith("<!doctype html>")
    assert '<html lang="de">' in html
    assert "<title>Rechnung</title>" in html
    assert html.count('@font-face { font-family: "Inter"') == 8
    assert "data:font/woff2;base64," in html
    assert '<div class="watermark" aria-hidden="true"><span>Entwurf</span></div>' in html
    # Escaped user content, company and address.
    assert "Muster &amp; Co GmbH" in html
    assert "Konzept &amp; &lt;Umsetzung&gt;" in html
    assert "Muster &amp; Co GmbH · Bahnhofstrasse 1 · 8001 Zürich" in html
    for line in ("Beispiel AG", "z. Hd. Anna Muster", "Marktgasse 5", "3011 Bern"):
        assert f"<div>{line}</div>" in html
    assert "Schweiz" not in html
    # Facts next to the address.
    assert '<dt>Rechnungs-Nr.</dt><dd class="pending">folgt beim Ausstellen</dd>' in html
    assert "<dt>Kunden-Nr.</dt><dd>1001</dd>" in html
    assert "<dt>Datum</dt><dd>09.03.2026</dd>" in html
    assert "<dt>Fällig am</dt><dd>08.04.2026</dd>" in html
    assert "<dt>Leistungszeitraum</dt><dd>01.02.2026 – 28.02.2026</dd>" in html
    assert "<dt>Ihre Referenz</dt><dd>PO-7</dd>" in html
    assert "Ihre UID" not in html
    assert "<h1>Rechnung</h1>" in html
    assert '<p class="subject">Website</p>' in html
    # Lines: positions count items only, text lines are headings.
    assert f'<td class="num">12.5{NBSP}Std.</td>' in html
    assert '<td class="num">1’200.00</td>' in html
    assert f"abzüglich 10{NBSP}%" in html
    assert f'<td class="num">8.1{NBSP}%</td>' in html
    assert '<td class="num">13’500.00</td>' in html
    assert '<td class="pos">2</td>' in html
    assert "Phase 2<span" in html
    assert '<td class="num">3</td>' in html
    # Totals in order, with the discount, the tax per rate and the rounding.
    labels = [
        "Zwischensumme",
        f"Rabatt 5{NBSP}%",
        "Total netto",
        f"MWST 8.1{NBSP}% auf 12’825.00",
        f"MWST 2.6{NBSP}% auf 35.20",
        "Total CHF",
    ]
    positions = [html.index(f">{label}<") for label in labels]
    assert positions == sorted(positions)
    assert "Preise inkl." not in html
    # Texts with placeholders.
    assert '<p class="text">Guten Tag Beispiel AG</p>' in html
    assert (
        "Zahlbar bis 08.04.2026, Nr. (folgt beim Ausstellen), 13’899.95 CHF vom 09.03.2026,"
        " Muster &amp; Co GmbH" in html
    )
    assert "Danke {unbekannt}" in html
    assert 'class="notice"' not in html
    # Footer.
    assert '<div class="company"><span>Muster &amp; Co GmbH</span>' in html
    assert "<span>+41 44 000 00 00</span><span>info@muster.example</span>" in html
    assert "<span>IBAN CH93 0076 2011 6238 5295 7</span><span>BIC POFICHBEXXX</span>" in html
    assert "<span>MWST-Nr. CHE-123.456.788 MWST</span>" in html
    assert "<span>Steuernummer 12/345</span><span>Handelsregister CH-020.4.000.000-0</span>" in html


@pytest.mark.parametrize(
    ("register", "language", "lines"),
    [
        # Footer lines do not wrap: each part of a long entry gets its own line.
        (
            "Amtsgericht Kempten, HRB 12345",
            Language.DE,
            ["Handelsregister Amtsgericht Kempten", "HRB 12345"],
        ),
        (
            "FN 123456a, Landesgericht Feldkirch",
            Language.EN,
            ["Commercial register FN 123456a", "Landesgericht Feldkirch"],
        ),
        # An entry that names its register is not labelled twice, in either language.
        (
            "Handelsregister des Kantons Zürich, CHE-123.456.789",
            Language.EN,
            ["Handelsregister des Kantons Zürich", "CHE-123.456.789"],
        ),
        (
            "CHE-123.456.788,  handelsregister St. Gallen, ",
            Language.DE,
            ["CHE-123.456.788", "handelsregister St. Gallen"],
        ),
        (" , ", Language.DE, []),
    ],
)
def test_the_register_entry_is_split_at_commas(
    store: Store, printing: PrintHandlers, register: str, language: Language, lines: list[str]
) -> None:
    assert store.company is not None
    store.company = replace(store.company, tax_number="", commercial_register=register)
    html = printing.preview_html(DocumentType.INVOICE, draft(language=language))
    legal = "".join(f"<span>{line}</span>" for line in ["MWST-Nr. CHE-123.456.788 MWST", *lines])
    if language is Language.EN:
        legal = legal.replace("MWST-Nr.", "VAT no.")
    assert f'<div class="legal">{legal}</div>' in html


def test_an_issued_reverse_charge_invoice_abroad(printing: PrintHandlers, store: Store) -> None:
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER],
        contact_person="",
        address=factories.address(
            street="Ring", house_number="", supplement="Postfach 3", country=CountryCode("AT")
        ),
        vat_number=VatNumber.parse("ATU12345678"),
    )
    store.logo = Logo(content=b"\x89PNG", media_type="image/png")
    documents = printing.documents
    created = documents.create(DocumentType.INVOICE, draft(currency=Currency.CHF, lines=(FOOD,)))
    issued = documents.issue(created.document.id).document
    html = printing.html(issued.id)
    assert 'class="watermark"' not in html
    assert f"<title>Rechnung {issued.number}</title>" in html
    assert f'<h1>Rechnung <span class="number">{issued.number}</span></h1>' in html
    assert f"<dt>Rechnungs-Nr.</dt><dd>{issued.number}</dd>" in html
    assert '<img src="data:image/png;base64,iVBORw==" alt="Muster &amp; Co GmbH">' in html
    for line in ("Ring", "Postfach 3", "8001 Zürich", "Österreich"):
        assert f"<div>{line}</div>" in html
    assert "<dt>Ihre UID</dt><dd>ATU12345678</dd>" in html
    assert (
        '<p class="notice">Übergang der Steuerschuld auf den Leistungsempfänger'
        " (Steuerschuldnerschaft des Leistungsempfängers, Reverse Charge).</p>"
    ) in html
    # No VAT: no rate column, no tax lines.
    assert '<th class="num">%</th>' not in html
    assert "MWST 2.6" not in html
    assert "Total netto" not in html
    assert ">Total CHF<" in html


def test_goods_to_a_private_customer_abroad(printing: PrintHandlers, store: Store) -> None:
    assert store.company is not None
    store.company = replace(
        store.company,
        address=factories.address(country=CountryCode("AT"), postal_code="1010", city="Wien"),
        vat_number=VatNumber.parse("ATU12345675"),
    )
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER], kind=CustomerKind.PERSON, first_name="Eva", last_name="Muster"
    )
    printer = LineInput(
        kind=LineKind.ITEM, description="Drucker", unit_price="300", supply=Supply.GOODS
    )
    created = printing.documents.create(
        DocumentType.INVOICE, draft(currency=Currency.CHF, lines=(HOURS, printer))
    )
    html = printing.html(created.document.id)
    # The service is taxed at home: rates are printed, the goods line at 0 %.
    assert '<th class="num">%</th>' in html
    assert f">USt. 20{NBSP}% auf 13.500,00</span>" in html
    assert html.count('<p class="notice">') == 1
    assert (
        '<p class="notice">Steuerfreie Ausfuhrlieferung (§ 6 Abs. 1 Z 1 i. V. m. § 7 UStG).</p>'
        in html
    )


def test_cancellations_quotes_gross_prices_and_english(printing: PrintHandlers) -> None:
    documents = printing.documents
    invoice = documents.issue(
        documents.create(DocumentType.INVOICE, draft(lines=(FOOD,))).document.id
    ).document
    # 37.05 + 0.96 VAT = 38.01, cash rounded to 38.00.
    invoice_html = printing.html(invoice.id)
    assert ">Rundung</span>" in invoice_html
    assert ">−0.01</span>" in invoice_html
    assert ">38.00</span>" in invoice_html
    cancellation = documents.cancel(invoice.id).document.cancelled_by_id
    assert cancellation is not None
    html = printing.html(cancellation)
    assert "<h1>Stornorechnung" in html
    assert "<dt>Storno-Nr.</dt>" in html
    assert f'<p class="cancels">Storniert die Rechnung {invoice.number}</p>' in html
    assert "Fällig am" not in html
    assert "Bankverbindung" not in html

    quote = printing.preview_html(
        DocumentType.QUOTE,
        draft(
            price_mode=PriceMode.GROSS,
            lines=(FOOD,),
            service_to=date(2026, 3, 1),
            discount_kind=DiscountKind.AMOUNT,
            discount_value="1",
        ),
    )
    assert "<dt>Angebots-Nr.</dt>" in quote
    assert "<dt>Gültig bis</dt><dd>08.04.2026</dd>" in quote
    assert "<dt>Leistungsdatum</dt><dd>01.03.2026</dd>" in quote
    assert ">Rabatt<" in quote
    assert "Total netto" not in quote
    assert f">enthaltene MWST 2.6{NBSP}% auf 35.14<" in quote
    assert '<p class="prices-gross">Preise inkl. MWST</p>' in quote

    english = printing.preview_html(
        DocumentType.INVOICE,
        draft(language=Language.EN, lines=(HOURS,), service_from=date(2026, 3, 2)),
    )
    assert '<html lang="en">' in english
    assert '<dt>Invoice no.</dt><dd class="pending">assigned when issued</dd>' in english
    assert "<dt>Date of service</dt><dd>2 March 2026</dd>" in english
    assert f'<td class="num">12.5{NBSP}h</td>' in english
    assert '<td class="num">1,200.00</td>' in english
    assert f">VAT 8.1{NBSP}% on 13,500.00<" in english
    assert "Attn. Anna Muster" in english
    assert "VAT no. CHE-123.456.788 MWST" in english


def test_french_documents_as_written_in_switzerland(printing: PrintHandlers) -> None:
    french = printing.preview_html(
        DocumentType.INVOICE,
        draft(language=Language.FR, lines=(HOURS,), service_from=date(2026, 3, 2)),
    )
    assert '<html lang="fr">' in french
    assert "<title>Facture</title>" in french
    assert '<dt>N° de facture</dt><dd class="pending">attribué à l’émission</dd>' in french
    assert "<dt>Date</dt><dd>9 mars 2026</dd>" in french
    assert "<dt>Échéance</dt><dd>8 avril 2026</dd>" in french
    assert "<dt>Date de la prestation</dt><dd>2 mars 2026</dd>" in french
    assert f'<td class="num">12.5{NBSP}h</td>' in french
    assert '<td class="num">1’200.00</td>' in french
    assert f">TVA 8.1{NBSP}% sur 13’500.00<" in french
    assert "à l’att. de Anna Muster" in french
    assert "N° TVA CHE-123.456.788 MWST" in french
    assert "Coordonnées bancaires" in french


def test_italian_documents_abroad(printing: PrintHandlers, store: Store) -> None:
    store.customers[CUSTOMER] = replace(
        store.customers[CUSTOMER],
        address=factories.address(country=CountryCode("DE"), postal_code="10115", city="Berlin"),
        vat_number=VatNumber.parse("DE123456789"),
    )
    piece = LineInput(kind=LineKind.ITEM, description="Libro", unit="C62", unit_price="20")
    documents = printing.documents
    quote = documents.create(
        DocumentType.QUOTE, draft(language=Language.IT, lines=(piece,))
    ).document
    html = printing.html(quote.id)
    assert '<html lang="it">' in html
    assert "<title>Offerta</title>" in html
    assert "<dt>N. offerta</dt>" in html
    assert "<dt>Valida fino al</dt><dd>8 aprile 2026</dd>" in html
    assert f'<td class="num">1{NBSP}pz.</td>' in html
    assert "<div>Germania</div>" in html
    assert "<dt>Vostro IDI</dt><dd>DE123456789</dd>" in html
    assert (
        '<p class="notice">Inversione contabile: l’imposta è dovuta dal destinatario della'
        " prestazione.</p>"
    ) in html


def test_german_companies_and_people(store: Store) -> None:
    store.company = factories.company(
        address=factories.address(postal_code="10115", city="Berlin", country=CountryCode("DE")),
        default_currency=Currency.EUR,
        vat_number=VatNumber.parse("DE123456789"),
    )
    store.customers[CUSTOMER] = factories.customer(
        id=CUSTOMER,
        kind=CustomerKind.PERSON,
        company_name="",
        first_name="Erika",
        last_name="Mustermann",
        address=factories.address(country=CountryCode("CH")),
    )
    html = printing_for(store).preview_html(
        DocumentType.INVOICE, draft(lines=(HOURS,), currency=Currency.EUR)
    )
    assert "<div>Erika Mustermann</div>" in html
    assert "<div>Schweiz</div>" in html
    assert '<td class="num">1.200,00</td>' in html
    assert f">USt. 19{NBSP}% auf 13.500,00<" in html
    assert ">Total EUR<" in html
    assert "<span>USt-IdNr. DE123456789</span>" in html
    # No account in EUR and no contact data: those footer columns are left out.
    assert 'class="bank"' not in html
    assert 'class="contact"' not in html


def test_german_documents_name_the_customers_vat_id_in_german_terms(store: Store) -> None:
    store.company = factories.company(
        address=factories.address(postal_code="10115", city="Berlin", country=CountryCode("DE")),
        default_currency=Currency.EUR,
        vat_number=VatNumber.parse("DE123456789"),
    )
    store.customers[CUSTOMER] = factories.customer(
        id=CUSTOMER,
        address=factories.address(postal_code="1010", city="Wien", country=CountryCode("AT")),
        vat_number=VatNumber.parse("ATU12345678"),
    )
    html = printing_for(store).preview_html(
        DocumentType.INVOICE, draft(lines=(HOURS,), currency=Currency.EUR)
    )
    assert "<dt>Ihre USt-IdNr.</dt><dd>ATU12345678</dd>" in html
    assert "Steuerschuldnerschaft des Leistungsempfängers." in html


def test_themes_replace_templates(store: Store, tmp_path: Path) -> None:
    store.company = factories.company()
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    (tmp_path / "document.css").write_text("body { color: hotpink; }", encoding="utf-8")
    html = printing_for(store, tmp_path).preview_html(DocumentType.INVOICE, draft(lines=(HOURS,)))
    assert "body { color: hotpink; }" in html
    assert "DIN 5008" not in html


def test_themes_of_earlier_versions_still_print_the_notices(store: Store, tmp_path: Path) -> None:
    store.company = factories.company()
    store.customers[CUSTOMER] = factories.customer(
        id=CUSTOMER,
        address=factories.address(country=CountryCode("US")),
    )
    printer = LineInput(
        kind=LineKind.ITEM, description="Drucker", unit_price="300", supply=Supply.GOODS
    )
    (tmp_path / "document.html.j2").write_text("<p>{{ notice }}</p>", encoding="utf-8")
    html = printing_for(store, tmp_path).preview_html(
        DocumentType.INVOICE, draft(lines=(HOURS, printer))
    )
    assert html == (
        "<p>Ort der Leistung im Ausland, nicht der MWST unterstellt.\n"
        "Steuerbefreite Ausfuhrlieferung (Art. 23 Abs. 2 Ziff. 1 MWSTG).</p>"
    )


def test_drafts_of_removed_customers_print_without_address(
    printing: PrintHandlers, store: Store
) -> None:
    created = printing.documents.create(DocumentType.INVOICE, draft(lines=(FOOD,)))
    del store.customers[CUSTOMER]
    html = printing.html(created.document.id)
    assert '<div class="recipient">\n      </div>' in html
    assert "Kunden-Nr." not in html


def test_css_strings_cannot_leave_the_style_element() -> None:
    text = 'A "B" \\ C\n</style><script>&'
    assert css_string(text) == 'A \\"B\\" \\\\ C\\A \\3C /style\\3E \\3C script\\3E \\26 '
    assert css_string("a\rb\fc") == "a\\D b\\C c"


def test_paper_footers_fill_the_three_margin_boxes(printing: PrintHandlers, store: Store) -> None:
    html = printing.preview_html(DocumentType.INVOICE, draft(lines=(FOOD,)))
    style = html[html.index("@page {\n") : html.index("</style>")]
    assert "@bottom-left {" in style
    # Company and contact share the left box; bank and legal data follow.
    assert 'content: "Muster \\26  Co GmbH\\A Bahnhofstrasse 1\\A 8001 Zürich\\A +41 44' in style
    assert (
        'content: "Bankverbindung CHF\\A Musterbank\\A Kontoinhaber: Muster GmbH\\A IBAN CH93'
        in style
    )
    assert 'content: "MWST-Nr. CHE-123.456.788 MWST' in style
    # The holder is left out when it is the company itself.
    store.company = factories.company(name=" muster  GMBH")
    same = printing.preview_html(DocumentType.INVOICE, draft(lines=(FOOD,)))
    assert "Kontoinhaber" not in same
    store.company = factories.company(vat_number=None)
    store.bank_accounts.clear()
    plain = printing.preview_html(DocumentType.INVOICE, draft(lines=(FOOD,)))
    assert plain.count('content: "";') == 2
