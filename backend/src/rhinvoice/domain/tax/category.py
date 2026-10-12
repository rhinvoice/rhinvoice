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
