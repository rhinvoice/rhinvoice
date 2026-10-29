"""How documents are laid out on paper: a template and a few choices.

Positions that the law or the envelope fix (address field, Swiss payment part)
are the same in every template; the choices change the look only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

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
