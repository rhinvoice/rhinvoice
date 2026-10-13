"""Writing off an invoice that will not be paid (bad debt).

The invoice was right and stays as it was issued: nothing is sent to the customer,
who still owes the amount. Only collecting it is given up. That sets a write-off
apart from a cancellation, which revokes a wrong invoice with a document of its own.

What the write-off means for the tax depends on how the company accounts for it,
which Rhinvoice does not know. It therefore only states the tax contained in the
amount (``tax_share``):

- CH: correction of the consideration in the period in which it is booked
  (Art. 41 Abs. 1 MWSTG, https://www.fedlex.admin.ch/eli/cc/2009/615/de); nothing
  to correct when accounting by received consideration (Art. 39 Abs. 2, Art. 40 Abs. 2).
- LI: the same wording (Art. 39 to 41 MWSTG, LGBl. 2009 Nr. 330,
  https://www.gesetze.li/konso/2009330000).
- DE: correction in the period in which the amount became uncollectible, and again
  when it is paid after all (§ 17 Abs. 2 Nr. 1 UStG,
  https://www.gesetze-im-internet.de/ustg_1980/__17.html).
- AT: the same (§ 16 Abs. 3 Z 1 UStG 1994,
  https://www.ris.bka.gv.at/GeltendeFassung.wxe?Abfrage=Bundesnormen&Gesetzesnummer=10004873).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import CurrencyMismatchError, ValidationError
from rhinvoice.domain.shared.money import Money, round_half_up
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID

    from rhinvoice.domain.document.calculation import Totals

MAX_NOTE = 500


class WriteOffReason(StrEnum):
    GONE = "gone"
    """The customer was dissolved or went bankrupt."""
    TIME_BARRED = "time_barred"
    SMALL_AMOUNT = "small_amount"
    """Collecting it would cost more than it brings."""
    UNTRACEABLE = "untraceable"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class WriteOff:
    """What was open of an invoice on the day collecting it was given up."""

    id: UUID
    written_off_on: date
    amount: Money
    reason: WriteOffReason
    recorded_at: datetime
    note: str = ""

    def __post_init__(self) -> None:
        if self.amount.amount <= 0:
            raise ValidationError("amount", "a write-off must be a positive amount")
        if self.amount != self.amount.round_to_minor():
            raise ValidationError("amount", "a write-off has at most two decimal places")
        object.__setattr__(self, "note", clean_text(self.note, "note", max_length=MAX_NOTE))


def tax_share(amount: Money, totals: Totals) -> Money:
    """Return the tax contained in ``amount`` of an invoice with these totals.

    The tax is spread evenly over the total: of half the invoice, half its tax.
    """
    if amount.currency is not totals.currency:
        raise CurrencyMismatchError(f"the amount must be in {totals.currency}")
    share = amount.amount * totals.tax.amount / totals.total.amount
    return Money(round_half_up(share, totals.currency.minor_step), totals.currency)
