"""Print layouts: the template, the logo, the font and what the footer lists."""

import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from rhinvoice.application.company.handlers import CompanyHandlers
from rhinvoice.application.document.printing import PrintModel, ReminderPrint, sample_customer
from rhinvoice.application.errors import ConflictError, NotFoundError, UnavailableError
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.company.print_layout import (
    DEFAULT_INFO_BLOCK,
    FooterAccounts,
    InfoEntry,
    InfoField,
    InfoRow,
    LogoPosition,
    LogoSize,
    PrintFont,
    PrintLayout,
    PrintTemplate,
)
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.iban import Bic, Iban
from rhinvoice.domain.shared.money import Currency
from tests.helpers import raises_exactly
from tests.unit.application.fakes import STANDARD_LAYOUT, InMemoryUnitOfWork, Store
from tests.unit.domain import factories
from tests.unit.test_rendering import draft, printing_for

if TYPE_CHECKING:
    from collections.abc import Callable

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
    store.use_layout(layout)
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


class SamplePdf:
    def __init__(self) -> None:
        self.models: list[PrintModel] = []
        self.e_invoices: list[bytes | None] = []

    def pdf(self, model: PrintModel, e_invoice: bytes | None = None) -> bytes:
        self.models.append(model)
        self.e_invoices.append(e_invoice)
        return b"%PDF sample"

    def reminder_pdf(self, reminder: ReminderPrint) -> bytes:
        raise NotImplementedError


def layouts(store: Store) -> CompanyHandlers:
    return CompanyHandlers(uow=lambda: InMemoryUnitOfWork(store))


def test_layouts_are_added_as_copies_renamed_and_saved(store: Store) -> None:
    handlers = layouts(store)
    [standard] = handlers.list_print_layouts()
    assert (standard.name, standard.is_default, standard.layout) == (
        "Standard",
        True,
        PrintLayout(),
    )
    store.use_layout(PrintLayout(template=PrintTemplate.CLASSIC))
    trust = handlers.create_print_layout(" Treuhand ")
    # A copy of the default one, not the default itself.
    assert (trust.name, trust.is_default, trust.layout.template) == (
        "Treuhand",
        False,
        PrintTemplate.CLASSIC,
    )
    plain = handlers.update_print_layout(
        trust.id, "Treuhand", PrintLayout(template=PrintTemplate.PLAIN)
    )
    copy = handlers.create_print_layout("Behörden", copy_of=trust.id)
    assert copy.layout == plain.layout
    assert [named.name for named in handlers.list_print_layouts()] == [
        "Standard",
        "Behörden",
        "Treuhand",
    ]
    # Saving the default keeps it the default.
    saved = handlers.update_print_layout(STANDARD_LAYOUT.id, "Haupt", PrintLayout())
    assert (saved.name, saved.is_default) == ("Haupt", True)


def test_names_tell_layouts_apart(store: Store) -> None:
    handlers = layouts(store)
    trust = handlers.create_print_layout("Treuhand")
    attempts: list[Callable[[], object]] = [
        lambda: handlers.create_print_layout("standard"),
        lambda: handlers.update_print_layout(trust.id, " STANDARD ", PrintLayout()),
    ]
    for attempt in attempts:
        with raises_exactly(ConflictError, "another print layout has this name") as caught:
            attempt()
        assert caught.value.code == "print_layout_name_taken"
        assert caught.value.details == {"name": "another print layout has this name"}
    # Its own name is no conflict.
    assert handlers.update_print_layout(trust.id, "treuhand", PrintLayout()).name == "treuhand"


def test_at_most_twenty_layouts(store: Store) -> None:
    handlers = layouts(store)
    for index in range(19):
        handlers.create_print_layout(f"Vorlage {index}")
    with raises_exactly(ConflictError, "at most 20 print layouts") as caught:
        handlers.create_print_layout("Eine zu viel")
    assert caught.value.code == "too_many_print_layouts"


def test_a_default_is_made_even_when_none_is_left(store: Store) -> None:
    handlers = layouts(store)
    trust = handlers.create_print_layout("Treuhand")
    store.print_layouts[STANDARD_LAYOUT.id] = replace(STANDARD_LAYOUT, is_default=False)
    assert handlers.make_default_print_layout(trust.id).is_default
    assert [named.name for named in handlers.list_print_layouts() if named.is_default] == [
        "Treuhand"
    ]


def test_one_layout_is_the_default(store: Store) -> None:
    handlers = layouts(store)
    trust = handlers.create_print_layout("Treuhand")
    assert handlers.make_default_print_layout(STANDARD_LAYOUT.id).is_default
    chosen = handlers.make_default_print_layout(trust.id)
    assert chosen.is_default
    listed = handlers.list_print_layouts()
    assert [(named.name, named.is_default) for named in listed] == [
        ("Treuhand", True),
        ("Standard", False),
    ]
    with raises_exactly(ConflictError, "the default print layout cannot be deleted") as caught:
        handlers.delete_print_layout(trust.id)
    assert caught.value.code == "default_print_layout"
    handlers.delete_print_layout(STANDARD_LAYOUT.id)
    assert [named.name for named in handlers.list_print_layouts()] == ["Treuhand"]


def test_changes_lock_the_layouts_first(store: Store) -> None:
    """The database keeps one default only if changes run one after the other."""
    handlers = layouts(store)
    handlers.list_print_layouts()
    assert store.print_layout_locks == 0
    trust = handlers.create_print_layout("Treuhand")
    handlers.update_print_layout(trust.id, "Treuhand", PrintLayout())
    handlers.make_default_print_layout(trust.id)
    handlers.delete_print_layout(STANDARD_LAYOUT.id)
    assert store.print_layout_locks == 4


def test_unknown_layouts_are_not_found(store: Store) -> None:
    handlers = layouts(store)
    unknown = UUID(int=404)
    attempts: list[Callable[[], object]] = [
        lambda: handlers.create_print_layout("Kopie", copy_of=unknown),
        lambda: handlers.update_print_layout(unknown, "X", PrintLayout()),
        lambda: handlers.make_default_print_layout(unknown),
        lambda: handlers.delete_print_layout(unknown),
    ]
    for attempt in attempts:
        with raises_exactly(NotFoundError, "print layout not found"):
            attempt()


def test_a_document_prints_with_its_layout_its_customers_or_the_default(store: Store) -> None:
    handlers = layouts(store)
    trust = handlers.update_print_layout(
        handlers.create_print_layout("Treuhand").id,
        "Treuhand",
        PrintLayout(template=PrintTemplate.CLASSIC),
    )
    plain = handlers.update_print_layout(
        handlers.create_print_layout("Schlicht").id,
        "Schlicht",
        PrintLayout(template=PrintTemplate.PLAIN),
    )
    printing = printing_for(store)

    def page(**overrides: object) -> str:
        return printing.preview_html(DocumentType.INVOICE, draft(**overrides))

    assert '<body class="template-modern ' in page()
    store.customers[CUSTOMER] = replace(store.customers[CUSTOMER], print_layout_id=trust.id)
    assert '<body class="template-classic ' in page()
    assert '<body class="template-plain ' in page(print_layout_id=plain.id)
    # Issuing freezes the layout: changing or deleting it later changes nothing.
    created = printing.documents.create(DocumentType.INVOICE, draft(print_layout_id=plain.id))
    issued = printing.documents.issue(created.document.id).document
    assert created.document.content.print_layout_id == plain.id
    handlers.delete_print_layout(plain.id)
    assert '<body class="template-plain ' in printing.html(issued.id)
    # A deleted choice falls back to the customer's layout, then to the default.
    other = printing.documents.create(DocumentType.INVOICE, draft()).document
    assert '<body class="template-classic ' in printing.html(other.id)
    # Without a choice of its own, issuing freezes the customer's layout.
    customers = printing.documents.create(DocumentType.INVOICE, draft()).document
    frozen = printing.documents.issue(customers.id).document
    handlers.delete_print_layout(trust.id)
    assert '<body class="template-modern ' in printing.html(other.id)
    assert '<body class="template-classic ' in printing.html(frozen.id)


def test_a_choice_names_a_layout(store: Store) -> None:
    printing = printing_for(store)
    unknown = UUID(int=404)
    with raises_exactly(ValidationError, "unknown print layout") as caught:
        printing.documents.create(DocumentType.INVOICE, draft(print_layout_id=unknown))
    assert caught.value.details == {"print_layout_id": "unknown print layout"}


def test_the_sample_pdf_is_marked_and_needs_the_pdf_service(store: Store) -> None:
    printing = printing_for(store)
    with raises_exactly(
        UnavailableError, "PDFs need the Gotenberg service (RHINVOICE_GOTENBERG_URL)"
    ):
        printing.layout_sample_pdf(PrintLayout())
    # The latest invoice is an issued one.
    created = printing.documents.create(DocumentType.INVOICE, draft(subject="Neueste"))
    issued = printing.documents.issue(created.document.id).document
    assert issued.number is not None
    pdf = SamplePdf()
    content = replace(printing, pdf_renderer=pdf).layout_sample_pdf(
        PrintLayout(template=PrintTemplate.PLAIN)
    )
    assert content.startswith(b"%PDF")
    sample = pdf.models[-1]
    assert sample.sample
    assert sample.layout.template is PrintTemplate.PLAIN
    # Neither its number nor payment codes: the sample is no second copy to file or pay.
    assert sample.view.document.id == issued.id
    assert sample.view.document.number is None
    assert sample.is_draft
    # The sample carries no e-invoice.
    assert pdf.e_invoices == [None]
    html = printing.renderer.html(sample)
    assert '<div class="watermark" aria-hidden="true"><span>Muster</span></div>' in html
    assert issued.number not in html
    assert "Der QR-Zahlteil wird beim Ausstellen erstellt." in html
    # The issued invoice itself is untouched.
    assert store.documents[issued.id].document.number == issued.number


def test_the_preview_shows_the_latest_invoice(store: Store) -> None:
    printing = printing_for(store)
    created = printing.documents.create(DocumentType.INVOICE, draft(subject="Neueste"))
    html = printing.layout_preview_html(PrintLayout(template=PrintTemplate.PLAIN))
    assert '<body class="template-plain ' in html
    assert "Neueste" in html
    # The saved layout is not touched.
    assert store.print_layouts == {STANDARD_LAYOUT.id: STANDARD_LAYOUT}
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
    store.use_layout(ALL)
    created = printing.documents.create(DocumentType.INVOICE, draft())
    issued = printing.documents.issue(created.document.id)
    assert "EUR CH56" in footer(printing.html(issued.document.id))
    # Issued documents keep the layout and accounts of the day they were issued.
    store.use_layout(PrintLayout(template=PrintTemplate.PLAIN))
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
    store.use_layout(PrintLayout(template=PrintTemplate.PLAIN))
    assert '<body class="template-plain ' in printing.html(issued.id)


def _provider(store: Store, **overrides: object) -> BankAccount:
    values: dict[str, object] = {
        "iban": Iban.parse("CH5800791123000889012"),
        "holder": "Inkasso AG",
        "third_party": True,
        "holder_address": factories.address(street="Zahlweg", postal_code="4001", city="Basel"),
    }
    values.update(overrides)
    provider = factories.bank_account(**values)
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
    store.use_layout(ALL)
    printing = printing_for(store)
    html = printing.preview_html(DocumentType.INVOICE, draft(bank_account_id=provider.id))
    # Payee, IBAN and BIC one below the other.
    assert (
        "<dt>Zahlungsempfänger</dt><dd>Inkasso AG</dd>"
        "<dt>IBAN</dt><dd>CH58 0079 1123 0008 8901 2</dd>"
        "<dt>BIC</dt><dd>UBSWCHZH80A</dd>" in html
    )
    # Listed after the own accounts, only on documents paid to it.
    assert "Inkasso AG" in footer(html)
    assert footer(html).index("CH56 0483") < footer(html).index("CH58 0079")
    store.use_layout(PrintLayout())
    paid_to_it = printing.preview_html(
        DocumentType.INVOICE, draft(bank_account_id=provider.id, payment_text="")
    )
    assert "<dt>Zahlungsempfänger</dt><dd>Inkasso AG</dd>" in paid_to_it
    assert 'class="payment-text"' not in paid_to_it
    assert "CH93" not in footer(paid_to_it)
    assert "Zahlungsempfänger" not in printing.preview_html(DocumentType.INVOICE, draft())


def test_texts_name_the_holder_of_the_paid_account(store: Store) -> None:
    provider = _provider(
        store,
        holder_address=factories.address(
            street="Zahlweg",
            house_number="3",
            postal_code="40477",
            city="Düsseldorf",
            country=CountryCode("DE"),
        ),
    )
    printing = printing_for(store)
    text = "Abgetreten an {kontoinhaber}, {kontoinhaber_adresse}."

    def payment(**overrides: object) -> str:
        html = printing.preview_html(DocumentType.INVOICE, draft(payment_text=text, **overrides))
        found = re.search(r"<p>(Abgetreten an[^<]*)</p>", html)
        assert found is not None
        return found.group(1)

    # A third party's address, with its country when abroad.
    assert payment(bank_account_id=provider.id) == (
        "Abgetreten an Inkasso AG, Zahlweg 3, 40477 Düsseldorf, Deutschland."
    )
    # An own account: its holder at the company's address.
    assert payment() == "Abgetreten an Anna Muster, Bahnhofstrasse 1, 8001 Zürich."
    # No account in the document's currency: nothing to name.
    store.bank_accounts = {
        account.id: account
        for account in store.bank_accounts.values()
        if account.currency is not Currency.CHF
    }
    assert payment() == "Abgetreten an , ."


def test_own_accounts_name_no_payee(store: Store) -> None:
    html = render(store, PrintLayout())
    assert "Zahlungsempfänger" not in html
    assert 'class="payee' not in html


def meta(html: str) -> list[tuple[str, str]]:
    block = html[html.index('<dl class="meta">') : html.index("</dl>")]
    return re.findall(r"<dt>(.*?)</dt><dd(?: class=\"pending\")?>(.*?)</dd>", block)


def test_the_facts_print_in_the_layouts_order_with_their_fields(store: Store) -> None:
    layout = PrintLayout(
        info_block=(
            InfoEntry(InfoRow.DATE.value),
            InfoEntry(InfoField.PROJECT.value),
            InfoEntry(InfoRow.NUMBER.value),
            InfoEntry(InfoRow.CUSTOMER_NUMBER.value, shown=False),
            InfoEntry(InfoRow.DUE_DATE.value),
            InfoEntry(InfoRow.SERVICE_DATE.value, shown=False),
            InfoEntry("custom-0a1b2c3d", label="Objekt"),
            InfoEntry(InfoField.BUYER_ACCOUNTING.value),
            InfoEntry(InfoRow.REFERENCE.value),
        )
    )
    store.use_layout(layout)
    html = printing_for(store).preview_html(
        DocumentType.INVOICE,
        draft(
            reference="PO-7",
            fields=(("project", "Website"), ("custom-0a1b2c3d", "Haus Nord"), ("contract", "V-1")),
        ),
    )
    labels = [label for label, _ in meta(html)]
    # Hidden rows, fields without a value and fields the layout does not list stay out.
    assert labels == [
        "Datum",
        "Projekt",
        "Rechnungs-Nr.",
        "Fällig am",
        "Objekt",
        "Ihre Referenz",
    ]
    assert ("Projekt", "Website") in meta(html)
    assert ("Objekt", "Haus Nord") in meta(html)
    # The number not yet given is marked where it stands, not in the first row.
    assert '<dt>Rechnungs-Nr.</dt><dd class="pending">' in html
    assert '<dt>Datum</dt><dd class="pending">' not in html


def test_the_layout_preview_shows_where_empty_fields_go(store: Store) -> None:
    printing_for(store).documents.create(DocumentType.INVOICE, draft())
    layout = PrintLayout(info_block=(*DEFAULT_INFO_BLOCK, InfoEntry(InfoField.PROJECT.value)))
    assert ("Projekt", "…") in meta(printing_for(store).layout_preview_html(layout))
    # Documents themselves print a field only with a value.
    store.use_layout(layout)
    html = printing_for(store).preview_html(DocumentType.INVOICE, draft())
    assert "Projekt" not in [label for label, _ in meta(html)]


def test_the_default_layout_prints_the_facts_as_before(store: Store) -> None:
    html = render(store, PrintLayout())
    assert [label for label, _ in meta(html)] == [
        "Rechnungs-Nr.",
        "Kunden-Nr.",
        "Datum",
        "Fällig am",
        "Leistungsdatum",
    ]
    assert '<dt>Rechnungs-Nr.</dt><dd class="pending">' in html


def test_issued_documents_keep_their_rows_and_values(store: Store) -> None:
    printing = printing_for(store)
    store.use_layout(
        PrintLayout(info_block=(*DEFAULT_INFO_BLOCK, InfoEntry(InfoField.CONTRACT.value)))
    )
    created = printing.documents.create(
        DocumentType.INVOICE, draft(fields=(("contract", "V-2026-7"),))
    )
    issued = printing.documents.issue(created.document.id).document
    store.use_layout(PrintLayout())
    assert ("Vertrag", "V-2026-7") in meta(printing.html(issued.id))
