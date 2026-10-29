"""Print layouts: the template, the logo, the font and what the footer lists."""

import re
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from rhinvoice.application.company.handlers import CompanyHandlers
from rhinvoice.application.document.printing import sample_customer
from rhinvoice.application.errors import ConflictError
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.print_layout import (
    FooterAccounts,
    LogoPosition,
    LogoSize,
    PrintFont,
    PrintLayout,
    PrintTemplate,
)
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.iban import Bic, Iban
from rhinvoice.domain.shared.money import Currency
from tests.helpers import raises_exactly
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories
from tests.unit.test_rendering import draft, printing_for

CUSTOMER = UUID(int=1)
EUR_IBAN = "CH5604835012345678009"  # example IBAN
ALL = PrintLayout(footer_accounts=FooterAccounts.ALL)


@pytest.fixture
def store() -> Store:
    store = Store()
    store.company = factories.company(
        name="Pixelwerk",
        email=EmailAddress.parse("info@pixelwerk.example"),
        phone="+41 81 000 00 00",
    )
    chf = factories.bank_account(
        is_default=True, holder="Anna Muster", bic=Bic.parse("UBSWCHZH80A")
    )
    eur = factories.bank_account(
        currency=Currency.EUR,
        iban=Iban.parse(EUR_IBAN),
        is_default=True,
        holder="Anna Muster",
        bic=Bic.parse("UBSWCHZH80A"),
    )
    store.bank_accounts.update({chf.id: chf, eur.id: eur})
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    return store


def render(store: Store, layout: PrintLayout) -> str:
    store.print_layout = layout
    return printing_for(store).preview_html(DocumentType.INVOICE, draft())


def footer(html: str) -> str:
    # The template's own @page rule, after the stylesheet.
    return html[html.rindex("@page {\n") : html.index("</style>")]


def test_the_default_layout(store: Store) -> None:
    html = render(store, PrintLayout())
    assert '<body class="template-modern logo-right logo-medium font-sans">' in html
    # The modern template takes the company colour.
    assert store.company is not None
    assert f"--accent: oklch(0.46 0.12 {store.company.accent_hue});" in html
    assert '<div class="sender">' in html
    assert 'class="lines contact"' not in html
    assert '<th class="pos">' in html
    assert "Source Serif 4" not in html
    # Only the account the invoice is paid to.
    assert "IBAN CH93" in footer(html)
    assert "CH56" not in footer(html)


def test_choices_change_the_page(store: Store) -> None:
    layout = PrintLayout(
        template=PrintTemplate.CLASSIC,
        logo_position=LogoPosition.LEFT,
        logo_size=LogoSize.LARGE,
        font=PrintFont.SERIF,
        sender_line=False,
        contact=True,
        position_numbers=False,
    )
    html = render(store, layout)
    assert '<body class="template-classic logo-left logo-large font-serif">' in html
    assert "--accent: #1d2230;" in html
    assert '--font: "Source Serif 4", Georgia, "Times New Roman", serif;' in html
    assert '@font-face { font-family: "Source Serif 4"' in html
    # Hidden, so that the address stays in the envelope window.
    assert '<div class="sender hidden">' in html
    assert '<div class="lines contact">+41 81 000 00 00 · info@pixelwerk.example</div>' in html
    assert '<th class="pos">' not in html


def test_the_footer_can_list_every_account(store: Store) -> None:
    text = footer(render(store, ALL))
    # Accounts of one bank share a column: holder and BIC once.
    assert (
        'content: "Bankverbindung\\A Kontoinhaber: Anna Muster\\A Musterbank · BIC UBSWCHZH80A'
        '\\A CHF CH93 0076 2011 6238 5295 7\\A EUR CH56 0483 5012 3456 7800 9";' in text
    )


def boxes(text: str) -> list[list[str]]:
    contents = re.findall(r'content: "(.*)";', text)
    return [content.split("\\A ") if content else [] for content in contents]


def test_accounts_of_several_banks_share_one_short_column(store: Store) -> None:
    eur = next(a for a in store.bank_accounts.values() if a.currency is Currency.EUR)
    store.bank_accounts[eur.id] = replace(eur, bank_name="Andere Bank", holder="Pixelwerk")
    text = footer(render(store, ALL))
    assert (
        'content: "Bankverbindung\\A Musterbank · Anna Muster · BIC UBSWCHZH80A'
        "\\A CHF CH93 0076 2011 6238 5295 7\\A Andere Bank · BIC UBSWCHZH80A"
        '\\A EUR CH56 0483 5012 3456 7800 9";' in text
    )
    # The bottom margin holds about eight lines.
    assert [len(lines) <= 8 for lines in boxes(text)] == [True, True, True]


def test_banks_are_the_same_regardless_of_case_and_spacing(store: Store) -> None:
    eur = next(a for a in store.bank_accounts.values() if a.currency is Currency.EUR)
    store.bank_accounts[eur.id] = replace(eur, bank_name="MUSTERBANK ", holder="anna  muster")
    assert "Musterbank · BIC UBSWCHZH80A\\A CHF" in footer(render(store, ALL))


def test_different_bics_at_one_bank_are_named_per_account(store: Store) -> None:
    eur = next(a for a in store.bank_accounts.values() if a.currency is Currency.EUR)
    store.bank_accounts[eur.id] = replace(eur, bic=Bic.parse("POFICHBEXXX"))
    chf = next(a for a in store.bank_accounts.values() if a.currency is Currency.CHF)
    store.bank_accounts[chf.id] = replace(chf, bic=None)
    text = footer(render(store, ALL))
    assert "\\A Musterbank\\A CHF CH93 0076 2011 6238 5295 7\\A EUR CH56" in text
    assert "EUR CH56 0483 5012 3456 7800 9 · POFICHBEXXX" in text


def test_a_footer_without_accounts(store: Store) -> None:
    store.bank_accounts.clear()
    assert "Bankverbindung" not in footer(render(store, ALL))
    assert "Bankverbindung" not in footer(render(store, PrintLayout()))


def test_the_layout_is_saved(store: Store) -> None:
    handlers = CompanyHandlers(uow=lambda: InMemoryUnitOfWork(store))
    assert handlers.print_layout() == PrintLayout()
    layout = PrintLayout(template=PrintTemplate.PLAIN)
    assert handlers.save_print_layout(layout) == layout
    assert handlers.print_layout() == layout


def test_the_preview_shows_the_latest_invoice(store: Store) -> None:
    printing = printing_for(store)
    created = printing.documents.create(DocumentType.INVOICE, draft(subject="Neueste"))
    html = printing.layout_preview_html(PrintLayout(template=PrintTemplate.PLAIN))
    assert "template-plain" in html
    assert "Neueste" in html
    # The saved layout is not touched.
    assert store.print_layout is None
    assert created.document.id in store.documents


def test_the_preview_without_invoices_uses_a_sample(store: Store) -> None:
    html = printing_for(store).layout_preview_html(PrintLayout())
    assert "Beratung" in html
    assert "Muster AG" not in html


def test_the_preview_before_the_first_customer_uses_a_made_up_one(store: Store) -> None:
    store.customers.clear()
    html = printing_for(store).layout_preview_html(PrintLayout())
    assert "Beratung" in html
    assert "Muster AG" in html
    assert "8000 Zürich" in html
    # Shown only: neither the customer nor the invoice is saved.
    assert store.customers == {}
    assert store.documents == {}


def test_the_preview_needs_the_company(store: Store) -> None:
    store.customers.clear()
    store.company = None
    with raises_exactly(ConflictError, "set up the company before the preview") as caught:
        printing_for(store).layout_preview_html(PrintLayout())
    assert caught.value.code == "company_not_set_up"


@pytest.mark.parametrize(
    ("country", "name", "line"),
    [
        (Country.CH, "Muster AG", "Musterstrasse 1"),
        (Country.LI, "Muster AG", "9490 Vaduz"),
        (Country.DE, "Muster GmbH", "Musterstraße 1"),
        (Country.AT, "Muster GmbH", "1010 Wien"),
    ],
)
def test_the_made_up_customer_lives_in_the_company_country(
    country: Country, name: str, line: str
) -> None:
    customer = sample_customer(country, datetime(2026, 10, 23, tzinfo=UTC))
    assert customer.display_name == name
    assert customer.address.country.value == country.value
    assert line in " ".join(
        (
            f"{customer.address.street} {customer.address.house_number}",
            f"{customer.address.postal_code} {customer.address.city}",
        )
    )


def test_issued_documents_are_rendered_with_every_account(store: Store) -> None:
    printing = printing_for(store)
    store.print_layout = ALL
    created = printing.documents.create(DocumentType.INVOICE, draft())
    issued = printing.documents.issue(created.document.id)
    assert "EUR CH56" in footer(printing.html(issued.document.id))
    # Issued documents keep the layout and accounts of the day they were issued.
    store.print_layout = PrintLayout(template=PrintTemplate.PLAIN)
    store.bank_accounts.clear()
    html = printing.html(issued.document.id)
    assert "template-modern" in html
    assert "EUR CH56" in footer(html)


def test_documents_issued_before_layouts_existed_use_the_current_one(store: Store) -> None:
    printing = printing_for(store)
    created = printing.documents.create(DocumentType.INVOICE, draft())
    issued = printing.documents.issue(created.document.id).document
    snapshot = replace(issued.issued_snapshot, layout=None, accounts=None)
    store.documents[issued.id] = replace(
        store.documents[issued.id], document=replace(issued, snapshot=snapshot)
    )
    store.print_layout = PrintLayout(template=PrintTemplate.PLAIN)
    assert "template-plain" in printing.html(issued.id)


def _provider(store: Store, **overrides: object) -> BankAccount:
    provider = factories.bank_account(
        iban=Iban.parse("CH5800791123000889012"),
        holder="Inkasso AG",
        third_party=True,
        holder_address=factories.address(street="Zahlweg", postal_code="4001", city="Basel"),
        **overrides,
    )
    store.bank_accounts[provider.id] = provider
    return provider


def test_the_footer_can_list_no_account(store: Store) -> None:
    text = footer(render(store, PrintLayout(footer_accounts=FooterAccounts.NONE)))
    assert "IBAN" not in text
    assert "Bankverbindung" not in text


def test_all_accounts_are_the_own_ones(store: Store) -> None:
    _provider(store)
    text = footer(render(store, ALL))
    assert "CH93 0076" in text
    assert "CH56 0483" in text
    assert "Inkasso AG" not in text
    assert "CH58" not in text


def test_a_document_paid_to_a_third_party_names_it(store: Store) -> None:
    provider = _provider(store, bic=Bic.parse("UBSWCHZH80A"))
    store.print_layout = ALL
    printing = printing_for(store)
    html = printing.preview_html(DocumentType.INVOICE, draft(bank_account_id=provider.id))
    assert (
        '<p class="payee">Zahlung an: Inkasso AG · IBAN CH58 0079 1123 0008 8901 2'
        " · BIC UBSWCHZH80A</p>" in html
    )
    # Listed after the own accounts, only on documents paid to it.
    assert "Inkasso AG" in footer(html)
    assert footer(html).index("CH56 0483") < footer(html).index("CH58 0079")
    store.print_layout = PrintLayout()
    paid_to_it = printing.preview_html(
        DocumentType.INVOICE, draft(bank_account_id=provider.id, payment_text="")
    )
    assert '<p class="payee">Zahlung an: Inkasso AG' in paid_to_it
    assert '<p class="payment-text">' not in paid_to_it
    assert "CH93" not in footer(paid_to_it)
    assert "Zahlung an" not in printing.preview_html(DocumentType.INVOICE, draft())


def test_own_accounts_name_no_payee(store: Store) -> None:
    html = render(store, PrintLayout())
    assert "Zahlung an" not in html
    assert 'class="payee' not in html
