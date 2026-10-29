"""The print template: one HTML page per document, for the preview, the view and the PDF.

All decisions (what to print, labels, number formats) are made here in
Python; the Jinja2 template only lays the prepared strings out. Templates can
be overridden by placing files of the same name in a theme directory.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import TYPE_CHECKING

from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    PackageLoader,
    select_autoescape,
)
from markupsafe import Markup

from rhinvoice.domain.company.print_layout import PrintFont, PrintTemplate, accounts_in_footer
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import DiscountKind, LineKind, PriceMode
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.text.template import Placeholder, fill_placeholders
from rhinvoice.infrastructure.payment.epc import epc_account, epc_qr
from rhinvoice.infrastructure.payment.qr_bill import qr_bill_account, swiss_qr_bill
from rhinvoice.infrastructure.rendering.country_names import country_name
from rhinvoice.infrastructure.rendering.formatting import (
    NO_BREAK_SPACE,
    PrintLocale,
    day,
    money,
    number,
    percent,
    unit_price,
)
from rhinvoice.infrastructure.rendering.labels import (
    LABELS,
    REMINDER_TITLES,
    TITLES,
)

if TYPE_CHECKING:
    from datetime import date
    from decimal import Decimal
    from pathlib import Path

    from rhinvoice.application.document.printing import PrintModel, ReminderPrint
    from rhinvoice.domain.company.bank_account import BankAccount
    from rhinvoice.domain.company.company import Company
    from rhinvoice.domain.country.profile import CountryTerms
    from rhinvoice.domain.customer.customer import Customer
    from rhinvoice.domain.shared.address import Address

# Static weights, not the variable font: Chromium embeds variable fonts as Type 3
# fonts, which do not survive the conversion to PDF/A.
FONT_WEIGHTS = (400, 500, 600, 700)
FONT_SUBSETS = {
    "latin": (
        "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,"
        "U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
    ),
    "latin-ext": (
        "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,"
        "U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,"
        "U+2C60-2C7F,U+A720-A7FF"
    ),
}
SEPARATOR = " " + chr(0x00B7) + " "
EN_DASH = " " + chr(0x2013) + " "


@dataclass(frozen=True, slots=True)
class FontFace:
    family: str
    weight: int
    unicode_range: str
    source: str
    """The woff2 file as a data URI, so the page needs no other request."""


SERIF_WEIGHTS = (400, 600)
SANS_STACK = '"Inter", "Helvetica Neue", Arial, sans-serif'
SERIF_STACK = '"Source Serif 4", Georgia, "Times New Roman", serif'


@cache
def _font_faces(family: str, file_prefix: str, weights: tuple[int, ...]) -> tuple[FontFace, ...]:
    """Read the faces of one family once, as data URIs."""
    folder = files("rhinvoice.infrastructure.rendering") / "fonts"
    return tuple(
        FontFace(
            family=family,
            weight=weight,
            unicode_range=unicode_range,
            source="data:font/woff2;base64,"
            + base64.b64encode(
                (folder / f"{file_prefix}-{subset}-{weight}-normal.woff2").read_bytes()
            ).decode(),
        )
        for weight in weights
        for subset, unicode_range in FONT_SUBSETS.items()
    )


def _fonts(font: PrintFont) -> tuple[FontFace, ...]:
    """Return the faces of the template: Inter always (numbers), the serif on demand."""
    inter = _font_faces("Inter", "inter", FONT_WEIGHTS)
    if font is PrintFont.SERIF:
        return inter + _font_faces("Source Serif 4", "source-serif-4", SERIF_WEIGHTS)
    return inter


@dataclass(frozen=True, slots=True)
class PrintLine:
    kind: str
    """"item" or "text"."""
    position: str
    description: str
    details: str
    quantity: str
    price: str
    rate: str
    amount: str
    line_id: str


@dataclass(frozen=True, slots=True)
class TotalRow:
    label: str
    value: str
    emphasis: bool = False


class JinjaDocumentRenderer:
    def __init__(self, theme_dir: Path | None = None) -> None:
        loaders: list[BaseLoader] = [] if theme_dir is None else [FileSystemLoader(theme_dir)]
        loaders.append(PackageLoader("rhinvoice.infrastructure.rendering", "templates"))
        self._environment = Environment(
            loader=ChoiceLoader(loaders),
            autoescape=select_autoescape(default=True, default_for_string=True),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def html(self, model: PrintModel) -> str:
        template = self._environment.get_template("document.html.j2")
        return template.render(**_context(model), fonts=_fonts(model.layout.font))

    def reminder_html(self, reminder: ReminderPrint) -> str:
        template = self._environment.get_template("reminder.html.j2")
        return template.render(
            **_reminder_context(reminder), fonts=_fonts(reminder.model.layout.font)
        )


@dataclass(frozen=True, slots=True)
class _Setting:
    """What every part of the page needs: language, number format and labels."""

    language: Language
    locale: PrintLocale
    labels: dict[str, str]
    terms: CountryTerms

    @property
    def tax(self) -> str:
        return self.terms.tax_name

    def amount(self, value: Decimal) -> str:
        return money(value, self.locale)


def _setting(model: PrintModel) -> _Setting:
    language = model.view.document.content.language
    profile = profile_of(model.company.country)
    return _Setting(
        language=language,
        locale=PrintLocale.of(language, profile.number_style),
        labels=LABELS[language],
        terms=profile.terms[language],
    )


def _context(model: PrintModel) -> dict[str, object]:
    document = model.view.document
    content = document.content
    company = model.company
    language = content.language
    setting = _setting(model)
    labels = setting.labels
    recipient = model.recipient
    values = _placeholder_values(model, setting)
    gross = content.price_mode is PriceMode.GROSS and content.charges_vat
    title = TITLES[language][document.type]
    layout = model.layout
    return {
        "language": language.value,
        "page_class": " ".join(
            (
                f"template-{layout.template.value}",
                f"logo-{layout.logo_position.value}",
                f"logo-{layout.logo_size.value}",
                f"font-{layout.font.value}",
            )
        ),
        # Constants and a number: safe inside the style element.
        "accent": Markup(_accent(model)),  # noqa: S704 - built from constants and an int
        "font_stack": Markup(SERIF_STACK if layout.font is PrintFont.SERIF else SANS_STACK),  # noqa: S704 - constants
        "show_sender_line": layout.sender_line,
        "head_contact": _contact_lines(company) if layout.contact else [],
        "position_numbers": layout.position_numbers,
        "title": title,
        "number": document.number or "",
        "number_pending": document.number is None,
        "draft": model.is_draft,
        "draft_label": labels["draft"],
        "logo": _logo(model),
        "company": company.name,
        "sender_line": SEPARATOR.join([company.name, *_company_lines(company.address)]),
        "company_lines": _company_lines(company.address),
        "recipient": [] if recipient is None else _recipient_lines(recipient, company, language),
        "meta": _meta(model, setting),
        "subject": content.subject,
        "cancels": (
            ""
            if model.cancelled_number is None
            else labels["cancels"].format(number=model.cancelled_number)
        ),
        "intro": fill_placeholders(content.intro_text, values),
        "labels": labels,
        "show_rate": content.charges_vat,
        "lines": _lines(model, setting),
        "prices_gross": labels["prices_gross"].format(tax=setting.tax) if gross else "",
        "totals": _totals(model, setting),
        "notices": [text for _, text in model.view.notices if text],
        # Themes written before 0.4 print one notice: all of them, one per line.
        "notice": model.view.notice,
        "payment": fill_placeholders(content.payment_text, values),
        "payee": _payee(model, labels),
        "closing": fill_placeholders(content.closing_text, values),
        "footer": _footer(model, language),
        "footer_boxes": _footer_boxes(_footer(model, language)),
        **_payment_codes(model, title),
    }


def _reminder_context(printed: ReminderPrint) -> dict[str, object]:
    """Build the invoice's page (head, address, footer, payment codes) with the reminder."""
    model = printed.model
    reminder = printed.reminder
    setting = _setting(model)
    labels = setting.labels
    invoice = model.view.document
    number = invoice.number or ""
    total = reminder.total
    values = reminder_placeholder_values(printed)
    meta = [(labels["reminder_date"], day(reminder.issued_on, setting.locale))]
    if model.recipient is not None:
        meta.append((labels["customer_number"], model.recipient.number))
    meta += [
        (labels["number_invoice"], number),
        (labels["pay_by"], day(reminder.due_date, setting.locale)),
    ]
    rows = [TotalRow(labels["open_amount"], setting.amount(reminder.open_amount.amount))]
    if reminder.fee.amount:
        rows.append(TotalRow(labels["fee"], setting.amount(reminder.fee.amount)))
    rows.append(
        TotalRow(
            f"{labels['total']} {total.currency.value}", setting.amount(total.amount), emphasis=True
        )
    )
    issued_total = model.view.totals.total
    return {
        **_context(model),
        "title": REMINDER_TITLES[setting.language][reminder.level],
        "number": "",
        "number_pending": False,
        "draft": False,
        "meta": meta,
        "intro": fill_placeholders(printed.text, values),
        "reminder_invoice": {
            "number": number,
            "date": day(model.issue_date, setting.locale),
            "due": "" if model.due_date is None else day(model.due_date, setting.locale),
            "total": setting.amount(issued_total.amount),
            "paid": setting.amount(issued_total.amount - reminder.open_amount.amount),
            "open": setting.amount(reminder.open_amount.amount),
        },
        "totals": rows,
    }


def _meta(model: PrintModel, setting: _Setting) -> list[tuple[str, str]]:
    """List the facts next to the address: number, customer number, dates, references."""
    document = model.view.document
    content = document.content
    labels = setting.labels
    number_label = {
        DocumentType.INVOICE: labels["number_invoice"],
        DocumentType.QUOTE: labels["number_quote"],
        DocumentType.CANCELLATION: labels["number_cancellation"],
    }[document.type]
    recipient = model.recipient
    meta = [(number_label, document.number or labels["number_pending"])]
    if recipient is not None:
        meta.append((labels["customer_number"], recipient.number))
    meta.append((labels["date"], day(model.issue_date, setting.locale)))
    if model.due_date is not None and document.type is not DocumentType.CANCELLATION:
        due = labels["due_quote"] if document.type is DocumentType.QUOTE else labels["due_invoice"]
        meta.append((due, day(model.due_date, setting.locale)))
    service = _service(content.service_from, content.service_to, setting)
    if not service and document.type is not DocumentType.QUOTE:
        # The date of supply is mandatory in DE and AT (§ 14 Abs. 4 Nr. 6 UStG,
        # § 11 Abs. 1 Z 3 lit. d UStG AT); without a period the supply took place on
        # the date of the invoice, which a cancellation repeats.
        supplied = model.cancelled_issue_date or model.issue_date
        service = [(labels["service_date"], day(supplied, setting.locale))]
    meta.extend(service)
    if content.reference:
        meta.append((labels["reference"], content.reference))
    if (
        {TaxTreatment.REVERSE_CHARGE, TaxTreatment.INTRA_COMMUNITY} & set(content.treatments)
        and recipient is not None
        and recipient.vat_number is not None
    ):
        meta.append((setting.terms.customer_vat_label, str(recipient.vat_number)))
    return meta


def _service(start: date | None, end: date | None, setting: _Setting) -> list[tuple[str, str]]:
    labels = setting.labels
    if start is not None and end is not None:
        period = f"{day(start, setting.locale)}{EN_DASH}{day(end, setting.locale)}"
        return [(labels["service_period"], period)]
    single = start or end
    return [] if single is None else [(labels["service_date"], day(single, setting.locale))]


def _lines(model: PrintModel, setting: _Setting) -> list[PrintLine]:
    content = model.view.document.content
    amounts = {line.line_id: line for line in model.view.totals.lines}
    lines: list[PrintLine] = []
    position = 0
    for line in content.lines:
        if line.kind is LineKind.TEXT:
            lines.append(
                PrintLine("text", "", line.description, line.details, "", "", "", "", str(line.id))
            )
            continue
        position += 1
        calculated = amounts[line.id]
        details = [line.details] if line.details else []
        if line.discount_percent:
            discount = percent(line.discount_percent, setting.locale)
            details.append(setting.labels["discount_line"].format(percent=discount))
        unit = "" if line.unit is None else line.unit.label(setting.language)
        quantity = number(line.quantity, setting.locale)
        lines.append(
            PrintLine(
                kind="item",
                position=str(position),
                description=line.description,
                details="\n".join(details),
                quantity=f"{quantity}{NO_BREAK_SPACE}{unit}" if unit else quantity,
                price=unit_price(line.unit_price, setting.locale),
                rate=(percent(calculated.tax_rate, setting.locale) if content.charges_vat else ""),
                amount=setting.amount(calculated.amount.amount),
                line_id=str(line.id),
            ),
        )
    return lines


def _totals(model: PrintModel, setting: _Setting) -> list[TotalRow]:
    content = model.view.document.content
    totals = model.view.totals
    labels = setting.labels
    rows: list[TotalRow] = []
    if totals.discount.amount:
        rows.append(TotalRow(labels["subtotal"], setting.amount(totals.subtotal.amount)))
        label = labels["discount"]
        if content.discount.kind is DiscountKind.PERCENT:
            label += " " + percent(content.discount.value, setting.locale)
        rows.append(TotalRow(label, setting.amount(-totals.discount.amount)))
    if content.charges_vat:
        gross = content.price_mode is PriceMode.GROSS
        if not gross:
            rows.append(TotalRow(labels["net"], setting.amount(totals.net.amount)))
        key = "tax_included" if gross else "tax_on"
        rows.extend(
            TotalRow(
                labels[key].format(
                    tax=setting.tax,
                    rate=percent(group.rate, setting.locale),
                    base=setting.amount(group.net.amount),
                ),
                setting.amount(group.tax.amount),
            )
            for group in totals.groups
            if group.rate
        )
    if totals.rounding.amount:
        rows.append(TotalRow(labels["rounding"], setting.amount(totals.rounding.amount)))
    total_label = f"{labels['total']} {totals.currency.value}"
    rows.append(TotalRow(total_label, setting.amount(totals.total.amount), emphasis=True))
    return rows


def placeholder_values(model: PrintModel) -> dict[Placeholder, str]:
    """Fill the placeholders of texts and mails as the document prints them."""
    return _placeholder_values(model, _setting(model))


def reminder_placeholder_values(printed: ReminderPrint) -> dict[Placeholder, str]:
    """Like the invoice's, with the new deadline and the amount the reminder asks for."""
    setting = _setting(printed.model)
    return {
        **_placeholder_values(printed.model, setting),
        Placeholder.DUE_DATE: day(printed.reminder.due_date, setting.locale),
        Placeholder.AMOUNT: setting.amount(printed.reminder.total.amount),
    }


def _placeholder_values(model: PrintModel, setting: _Setting) -> dict[Placeholder, str]:
    document = model.view.document
    recipient = model.recipient
    total = model.view.totals.total
    return {
        Placeholder.NUMBER: document.number or f"({setting.labels['number_pending']})",
        Placeholder.DATE: day(model.issue_date, setting.locale),
        Placeholder.DUE_DATE: "" if model.due_date is None else day(model.due_date, setting.locale),
        Placeholder.CUSTOMER: "" if recipient is None else recipient.display_name,
        Placeholder.AMOUNT: setting.amount(total.amount),
        Placeholder.CURRENCY: total.currency.value,
        Placeholder.COMPANY: model.company.name,
    }


def _accent(model: PrintModel) -> str:
    """Return the accent: the company colour in the modern template, ink in the others."""
    if model.layout.template is PrintTemplate.MODERN:
        # The app's primary colour (frontend/src/styles, --primary), a little darker for paper.
        return f"oklch(0.46 0.12 {model.company.accent_hue})"
    return "#1d2230"


def _contact_lines(company: Company) -> list[str]:
    email = "" if company.email is None else str(company.email)
    return [line for line in (company.phone, email, company.website) if line]


def _logo(model: PrintModel) -> str:
    if model.logo is None:
        return ""
    encoded = base64.b64encode(model.logo.content).decode()
    return f"data:{model.logo.media_type};base64,{encoded}"


def _street(address: Address) -> str:
    return " ".join(part for part in (address.street, address.house_number) if part)


def _company_lines(address: Address) -> list[str]:
    """List the sender's postal lines; its own country is not printed."""
    lines = [_street(address), address.supplement, f"{address.postal_code} {address.city}"]
    return [line for line in lines if line]


def _recipient_lines(customer: Customer, company: Company, language: Language) -> list[str]:
    address = customer.address
    attention = (
        f"{LABELS[language]['attention']} {customer.contact_person}"
        if customer.contact_person
        else ""
    )
    lines = [customer.display_name, attention]
    lines += [_street(address), address.supplement, f"{address.postal_code} {address.city}"]
    if address.country.value != company.address.country.value:
        lines.append(country_name(address.country.value, language))
    return [line for line in lines if line]


def _footer(model: PrintModel, language: Language) -> list[tuple[str, list[str]]]:
    """Columns of the footer as (kind, lines); empty columns are left out."""
    company = model.company
    labels = LABELS[language]
    columns: list[tuple[str, list[str]]] = [
        ("company", [company.name, *_company_lines(company.address)]),
    ]
    columns.append(("contact", _contact_lines(company)))
    columns.extend(("bank", lines) for lines in _bank_columns(model, labels))
    legal: list[str] = []
    if company.vat_number is not None:
        label = profile_of(company.country).terms[language].vat_number_label
        legal.append(f"{label} {company.vat_number}")
    if company.tax_number:
        legal.append(f"{labels['tax_number']} {company.tax_number}")
    legal += _register_lines(company.commercial_register, labels["register"])
    columns.append(("legal", legal))
    return [(kind, lines) for kind, lines in columns if lines]


def _register_lines(register: str, label: str) -> list[str]:
    """Split the register entry into footer lines, one per comma-separated part.

    Footer lines do not wrap, and entries such as "Handelsregister des Kantons
    Zürich, CHE-123.456.789" are long. The label goes in front unless the entry
    already names its register.
    """
    parts = [part.strip() for part in register.split(",") if part.strip()]
    if not parts:
        return []
    named = any(
        register_label.casefold() in register.casefold()
        for register_label in {LABELS[language]["register"] for language in Language}
    )
    return parts if named else [f"{label} {parts[0]}", *parts[1:]]


def _payee(model: PrintModel, labels: dict[str, str]) -> str:
    """Name the third party that collects the payment, with its IBAN; "" for own accounts."""
    account = model.bank_account
    if account is None or not account.third_party:
        return ""
    parts = [f"{labels['pay_to']} {account.holder}", f"IBAN {account.iban.formatted()}"]
    if account.bic is not None:
        parts.append(f"BIC {account.bic.value}")
    return SEPARATOR.join(parts)


def _bank_columns(model: PrintModel, labels: dict[str, str]) -> list[list[str]]:
    """List the bank details as one footer column, short enough for the bottom margin.

    Accounts of one bank share the bank's name, the holder and the BIC; several
    banks are listed one after the other, each in two to four lines.
    """
    company = model.company
    accounts = list(
        accounts_in_footer(model.layout.footer_accounts, model.bank_account, model.accounts)
    )
    if not accounts:
        return []
    banks: dict[tuple[str, str], list[BankAccount]] = {}
    for account in accounts:
        banks.setdefault((_name_key(account.bank_name), _name_key(account.holder)), []).append(
            account
        )
    holders = {key[1] for key in banks}
    # A sole proprietor's account is in their own name, not the trade name.
    holder = accounts[0].holder
    holder_line = (
        []
        if len(holders) > 1 or _same_name(holder, company.name)
        else [f"{labels['holder']} {holder}"]
    )
    if len(accounts) == 1:
        [account] = accounts
        return [
            [
                f"{labels['bank']} {account.currency.value}",
                account.bank_name,
                *holder_line,
                f"IBAN {account.iban.formatted()}",
                *([] if account.bic is None else [f"BIC {account.bic.value}"]),
            ]
        ]
    lines = [labels["bank"], *holder_line]
    for group in banks.values():
        bics = {None if account.bic is None else account.bic.value for account in group}
        shared_bic = bics.pop() if len(bics) == 1 else None
        first = group[0]
        names = [first.bank_name]
        if len(holders) > 1 and not _same_name(first.holder, company.name):
            names.append(first.holder)
        if shared_bic is not None:
            names.append(f"BIC {shared_bic}")
        lines.append(SEPARATOR.join(names))
        lines += [
            f"{account.currency.value} {account.iban.formatted()}"
            + ("" if shared_bic is not None or account.bic is None else f" · {account.bic.value}")
            for account in group
        ]
    return [lines]


def _name_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def _same_name(first: str, second: str) -> bool:
    """Compare names regardless of case and spacing ("MUSTER  GmbH" is "Muster GmbH")."""
    return _name_key(first) == _name_key(second)


FOOTER_BOXES = ("bottom-left", "bottom-center", "bottom-right")


def css_string(text: str) -> str:
    """Escape text for a double-quoted CSS string inside a <style> element."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    # Every CSS line break (LF, CR, FF) as an escape: a raw one would end the string.
    replacements = (("\n", "A"), ("\r", "D"), ("\f", "C"), ("<", "3C"), (">", "3E"), ("&", "26"))
    for character, code in replacements:
        escaped = escaped.replace(character, f"\\{code} ")
    return escaped


def _footer_boxes(columns: list[tuple[str, list[str]]]) -> list[tuple[str, Markup]]:
    """Spread the footer columns over the three bottom margin boxes of the page."""
    texts = [lines for _kind, lines in columns]
    # More columns than boxes: company and contact share the left box, then the next.
    while len(texts) > len(FOOTER_BOXES):
        texts = [texts[0] + texts[1], *texts[2:]]
    # Empty boxes still carry the separator line across the page.
    texts += [[] for _ in range(len(FOOTER_BOXES) - len(texts))]
    return [
        (box, Markup(css_string("\n".join(lines))))  # noqa: S704 - escaped for CSS above
        for box, lines in zip(FOOTER_BOXES, texts, strict=True)
    ]


def _payment_codes(model: PrintModel, title: str) -> dict[str, object]:
    """QR-bill (CH/LI) and EPC QR code (DE/AT, CH/LI to the EEA); drafts show where they will be."""
    number = model.view.document.number
    remittance = title if number is None else f"{title} {number}"
    return {
        "qr_bill": _markup(swiss_qr_bill(model, remittance)),
        "qr_bill_pending": model.is_draft and qr_bill_account(model) is not None,
        "epc_qr": _markup(epc_qr(model, remittance)),
        "epc_pending": model.is_draft and epc_account(model) is not None,
    }


def _markup(svg: str | None) -> Markup | None:
    """SVG from the payment code libraries, which escape the data they draw."""
    return None if svg is None else Markup(svg)  # noqa: S704 - generated, escaped SVG
