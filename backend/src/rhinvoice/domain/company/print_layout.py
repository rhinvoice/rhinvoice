"""How documents are laid out on paper: a template and a few choices.

Positions that the law or the envelope fix (address field, Swiss payment part)
are the same in every template; the choices change the look only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


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
    """Every bank account, e.g. CHF and EUR."""


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
