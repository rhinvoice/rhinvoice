from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rhinvoice.domain.tax.treatment import TaxTreatment


class Supply(StrEnum):
    """What a line supplies: VAT treats goods crossing borders differently (ADR 0014)."""

    SERVICE = "service"
    GOODS = "goods"
    """Physical things that are delivered (shipped or handed over)."""


def line_treatment(
    supply: Supply, treatment: TaxTreatment, goods_treatment: TaxTreatment | None
) -> TaxTreatment:
    """Treatment of a line: goods have their own when the document names one."""
    if supply is Supply.GOODS and goods_treatment is not None:
        return goods_treatment
    return treatment
