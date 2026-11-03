from enum import StrEnum


class TaxCategory(StrEnum):
    """Which VAT rate of the country profile applies to a line."""

    STANDARD = "standard"
    REDUCED = "reduced"
    SPECIAL = "special"
    """CH/LI accommodation rate (Beherbergung)."""
    ZERO = "zero"
    """Taxable at 0 % (e.g. exports)."""
    EXEMPT = "exempt"
    """Exempt from VAT (e.g. CH Art. 21 MWSTG, DE § 4 UStG)."""
    PASS_THROUGH = "pass_through"  # noqa: S105 - a tax category, no password
    """Paid in the customer's name and for the customer's account (durchlaufender Posten).

    Not part of the taxable amount: DE § 10 Abs. 1 Satz 4 UStG, AT § 4 Abs. 3 UStG 1994,
    CH and LI Art. 24 Abs. 6 lit. b MWSTG (there only when shown separately). Such a line
    carries no VAT, belongs to no VAT group and takes no document discount (ADR 0039).
    """
