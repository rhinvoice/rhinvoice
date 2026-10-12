from enum import StrEnum

from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.treatment import TaxTreatment


class VatCode(StrEnum):
    """UNCL5305 duty/tax category codes as used by EN 16931 (e-invoicing)."""

    STANDARD = "S"
    ZERO = "Z"
    EXEMPT = "E"
    REVERSE_CHARGE = "AE"
    EXPORT = "G"
    INTRA_COMMUNITY = "K"


def vat_code(treatment: TaxTreatment, category: TaxCategory) -> VatCode:
    if treatment is TaxTreatment.REVERSE_CHARGE:
        return VatCode.REVERSE_CHARGE
    if treatment in {TaxTreatment.EXPORT, TaxTreatment.GOODS_EXPORT}:
        return VatCode.EXPORT
    if treatment is TaxTreatment.INTRA_COMMUNITY:
        return VatCode.INTRA_COMMUNITY
    if treatment is not TaxTreatment.DOMESTIC or category is TaxCategory.EXEMPT:
        return VatCode.EXEMPT
    if category is TaxCategory.ZERO:
        return VatCode.ZERO
    return VatCode.STANDARD
