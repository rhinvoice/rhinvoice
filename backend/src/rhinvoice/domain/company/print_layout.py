"""How documents are laid out on paper: a template and a few choices.

Positions that the law or the envelope fix (address field, Swiss payment part)
are the same in every template; the choices change the look only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from rhinvoice.domain.company.bank_account import BankAccount


class PrintTemplate(StrEnum):
    CLASSIC = "classic"
    """Logo and sender at the top, a grey band over the positions."""
    MODERN = "modern"
    """The company colour as accent, the total highlighted."""
    PLAIN = "plain"
    """Much white space, no colour."""


class LogoPosition(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class LogoSize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class PrintFont(StrEnum):
    SANS = "sans"
    """Inter."""
    SERIF = "serif"
    """Source Serif 4."""


class FooterAccounts(StrEnum):
    INVOICE_CURRENCY = "invoice_currency"
    """Only the account the document is paid to."""
    ALL = "all"
    """Every own bank account, e.g. CHF and EUR, and a third party's paid to."""
    NONE = "none"
    """No bank details in the footer (the payment part and QR codes stay)."""


def accounts_in_footer(
    choice: FooterAccounts, paying: BankAccount | None, accounts: Sequence[BankAccount]
) -> tuple[BankAccount, ...]:
    """Choose the accounts the footer lists.

    A third party's account appears only on documents paid to it, so "all" lists
    the company's own accounts plus the paying account when that is a third party's.
    """
    if choice is FooterAccounts.NONE:
        return ()
    if choice is FooterAccounts.ALL and accounts:
        listed = [account for account in accounts if not account.third_party]
        if paying is not None and paying.third_party:
            listed = [*listed, paying]
        return tuple(listed)
    return () if paying is None else (paying,)


class InfoRow(StrEnum):
    """A fact next to the address that Rhinvoice fills in itself."""

    NUMBER = "number"
    CUSTOMER_NUMBER = "customer_number"
    DATE = "date"
    DUE_DATE = "due_date"
    SERVICE_DATE = "service_date"
    """The date or period of supply.

    Mandatory on invoices (§ 14 Abs. 4 Nr. 6 UStG, § 11 Abs. 1 Z 3 lit. d UStG AT); a
    layout may hide it for documents that state it in their positions. The e-invoice
    keeps it either way (BT-72).
    """
    REFERENCE = "reference"


REQUIRED_ROWS = frozenset({InfoRow.NUMBER, InfoRow.DATE})
"""Rows that every document shows."""


class InfoField(StrEnum):
    """A reference with a value per document that the e-invoice carries too (EN 16931)."""

    PROJECT = "project"
    """BT-11, the project reference."""
    CONTRACT = "contract"
    """BT-12, the contract reference."""
    PURCHASE_ORDER = "purchase_order"
    """BT-13, the buyer's purchase order."""
    SALES_ORDER = "sales_order"
    """BT-14, the seller's own order number."""
    DESPATCH_ADVICE = "despatch_advice"
    """BT-16, the delivery note."""
    TENDER = "tender"
    """BT-17, the tender or lot of a public procurement."""
    INVOICED_OBJECT = "invoiced_object"
    """BT-18, e.g. a meter, a subscription or a vehicle."""
    BUYER_ACCOUNTING = "buyer_accounting"
    """BT-19, the buyer's cost centre or account."""


_CUSTOM_KEY = re.compile(r"custom-[0-9a-f]{8}")
MAX_INFO_ENTRIES = 24
"""The six rows, the eight reference fields and ten fields of the user's own."""
MAX_FIELD_LABEL = 40
_ROWS = frozenset(row.value for row in InfoRow)
_FIELDS = frozenset(field.value for field in InfoField)
MAX_INFO_KEY = max(len(key) for key in (*_ROWS, *_FIELDS, "custom-00000000"))
"""The longest key of a row or a field ("buyer_accounting")."""


def is_field_key(key: str) -> bool:
    """Whether ``key`` names a field with a value per document: a reference or a custom one."""
    return key in _FIELDS or _CUSTOM_KEY.fullmatch(key) is not None


@dataclass(frozen=True, slots=True)
class InfoEntry:
    """One line of the facts next to the address, in the order they print."""

    key: str
    """An InfoRow, an InfoField or a custom field: "custom-" and 8 hex digits."""
    shown: bool = True
    """Rows only: whether the row prints. A field leaves the block by being removed."""
    label: str = ""
    """Custom fields only: the name printed next to the value."""

    def __post_init__(self) -> None:
        if self.key in _ROWS:
            if not self.shown and InfoRow(self.key) in REQUIRED_ROWS:
                raise ValidationError("info_block", f"the row {self.key} is always shown")
            if self.label:
                raise ValidationError("info_block", "only custom fields take a label")
            return
        if not is_field_key(self.key):
            raise ValidationError("info_block", f"unknown row {self.key}")
        if not self.shown:
            raise ValidationError("info_block", "a field is removed, not hidden")
        if self.key in _FIELDS:
            if self.label:
                raise ValidationError("info_block", "only custom fields take a label")
            return
        label = clean_text(self.label, "info_block", max_length=MAX_FIELD_LABEL, required=True)
        object.__setattr__(self, "label", label)

    @property
    def is_field(self) -> bool:
        return self.key not in _ROWS


DEFAULT_INFO_BLOCK = tuple(InfoEntry(row.value) for row in InfoRow)
"""The facts as documents printed them before layouts listed them."""


def _check_info_block(entries: tuple[InfoEntry, ...]) -> None:
    keys = [entry.key for entry in entries]
    if len(set(keys)) != len(keys):
        raise ValidationError("info_block", "each row appears once")
    if not _ROWS.issubset(keys):
        raise ValidationError("info_block", "every row is listed, shown or hidden")
    if len(entries) > MAX_INFO_ENTRIES:
        raise ValidationError("info_block", f"at most {MAX_INFO_ENTRIES} rows")


@dataclass(frozen=True, slots=True)
class PrintLayout:
    template: PrintTemplate = PrintTemplate.MODERN
    logo_position: LogoPosition = LogoPosition.RIGHT
    logo_size: LogoSize = LogoSize.MEDIUM
    font: PrintFont = PrintFont.SANS
    sender_line: bool = True
    """The small sender line above the address (window envelopes)."""
    contact: bool = False
    """Phone, e-mail and website in the head (the footer has them anyway)."""
    position_numbers: bool = True
    footer_accounts: FooterAccounts = FooterAccounts.INVOICE_CURRENCY
    e_invoice: bool = True
    """Embed the invoice as e-invoice (ZUGFeRD / Factur-X, EN 16931) in the PDF."""
    info_block: tuple[InfoEntry, ...] = DEFAULT_INFO_BLOCK
    """The facts next to the address, in order: Rhinvoice's rows and the fields."""

    def __post_init__(self) -> None:
        _check_info_block(self.info_block)

    def shows(self, row: InfoRow) -> bool:
        return any(entry.key == row.value and entry.shown for entry in self.info_block)

    @property
    def field_keys(self) -> tuple[str, ...]:
        """The fields whose values documents print, in order."""
        return tuple(entry.key for entry in self.info_block if entry.is_field)


MAX_LAYOUT_NAME = 60
MAX_LAYOUTS = 20
"""Named print layouts of an installation, the default one included."""


@dataclass(frozen=True, slots=True)
class NamedLayout:
    """A print layout with a name, e.g. "Standard" or "Treuhand"; one is the default (#48)."""

    id: UUID
    name: str
    layout: PrintLayout
    is_default: bool = False

    def __post_init__(self) -> None:
        name = clean_text(self.name, "name", max_length=MAX_LAYOUT_NAME, required=True)
        object.__setattr__(self, "name", name)


def layout_for(
    layouts: Sequence[NamedLayout], chosen: UUID | None, customers: UUID | None
) -> NamedLayout:
    """Return the layout a document prints with: its own, else its customer's, else the default.

    A choice whose layout was deleted since falls through to the next one.
    """
    by_id = {named.id: named for named in layouts}
    for wanted in (chosen, customers):
        if wanted is not None and wanted in by_id:
            return by_id[wanted]
    return default_layout(layouts)


def default_layout(layouts: Sequence[NamedLayout]) -> NamedLayout:
    """Return the default layout; the database keeps exactly one."""
    for named in layouts:
        if named.is_default:
            return named
    raise InvalidStateError("there is no default print layout")
