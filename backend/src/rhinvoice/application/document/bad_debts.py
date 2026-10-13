"""Bad debts per year: what was written off, what came in after all and the tax in it.

A write-off counts in the year it is dated, a later payment in the year it came in
(DE § 17 Abs. 2 Nr. 1 UStG and AT § 16 Abs. 3 Z 1 UStG correct the tax again in the
period of the payment; CH and LI Art. 41 MWSTG in the period it is booked). Whether
the tax is corrected at all depends on how the company accounts for it, so the tax
is only stated (see ``domain.document.write_off``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rhinvoice.domain.document.write_off import tax_share
from rhinvoice.domain.shared.money import Money

if TYPE_CHECKING:
    from rhinvoice.application.document.ports import BadDebt
    from rhinvoice.domain.shared.money import Currency


@dataclass(frozen=True, slots=True)
class BadDebtYear:
    year: int
    currency: Currency
    written_off: Money
    """Written off with a date in the year."""
    recovered: Money
    """Paid in the year on invoices written off before."""
    loss: Money
    """Written off less recovered; negative in a year that only brought payments."""
    net: Money
    tax: Money
    """Tax contained in the loss; ``net`` is the rest of it."""


def bad_debts_by_year(items: list[BadDebt]) -> list[BadDebtYear]:
    """Sum the write-offs per year and currency, the latest year first."""
    sums: dict[tuple[int, Currency], list[Money]] = {}

    def entry(year: int, currency: Currency) -> list[Money]:
        zero = Money.zero(currency)
        return sums.setdefault((year, currency), [zero, zero, zero])

    for item in items:
        currency = item.totals.currency
        amount = item.write_off.amount
        written = entry(item.write_off.written_off_on.year, currency)
        written[0] += amount
        written[2] += tax_share(amount, item.totals)
        for paid_on, paid in item.recoveries:
            recovered = entry(paid_on.year, currency)
            recovered[1] += paid
            recovered[2] -= tax_share(paid, item.totals)
    return [
        BadDebtYear(
            year=year,
            currency=currency,
            written_off=written_off,
            recovered=recovered,
            loss=written_off - recovered,
            net=written_off - recovered - tax,
            tax=tax,
        )
        for (year, currency), (written_off, recovered, tax) in sorted(
            sums.items(), key=lambda found: (-found[0][0], found[0][1])
        )
    ]
