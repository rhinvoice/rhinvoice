"""Recurring invoices: a plan writes the same invoice every month, quarter or year.

A plan holds the invoice's content as a template and the day of the next
invoice. On that day an invoice is created from the template, for the period
that starts then (as service period when wanted); the plan then moves on by
its interval, always counted from the first day, so the 31st stays the last
day of shorter months. See ADR 0016.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.document.document import MAX_LINES
from rhinvoice.domain.document.lines import Discount, LineKind
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.text import clean_multiline, clean_text

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from rhinvoice.domain.document.lines import DocumentLine, PriceMode
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.shared.money import Currency

MAX_NAME = 120
MAX_SUBJECT = 200
MAX_REFERENCE = 100
MAX_TEXT = 4000
MAX_CATCH_UP = 24
"""Periods one run writes at most for a plan (after a long downtime)."""


class Interval(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    HALF_YEARLY = "half_yearly"
    YEARLY = "yearly"

    @property
    def months(self) -> int:
        return {
            Interval.MONTHLY: 1,
            Interval.QUARTERLY: 3,
            Interval.HALF_YEARLY: 6,
            Interval.YEARLY: 12,
        }[self]


class PlanAction(StrEnum):
    """What happens on the day of an invoice."""

    DRAFT = "draft"
    """Create a draft to check and issue by hand."""
    ISSUE = "issue"
    """Issue the invoice right away."""
    SEND = "send"
    """Issue it and send it to the customer by mail."""


def add_months(start: date, months: int) -> date:
    """Move by whole months; a day the month lacks becomes its last day (31 Jan → 28 Feb)."""
    index = start.year * 12 + start.month - 1 + months
    year, month = divmod(index, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(start.day, last))


@dataclass(frozen=True, slots=True)
class InvoiceTemplate:
    """The content every invoice of a plan starts with."""

    currency: Currency
    price_mode: PriceMode
    lines: tuple[DocumentLine, ...]
    language: Language | None = None
    """None: the customer's or the company's language."""
    discount: Discount | None = None
    """None: the customer's default discount."""
    subject: str = ""
    reference: str = ""
    intro_text: str = ""
    payment_text: str = ""
    closing_text: str = ""

    def __post_init__(self) -> None:
        if not any(line.kind is LineKind.ITEM for line in self.lines):
            raise ValidationError(
                "lines",
                "the invoice needs at least one position with an amount",
                code="no_positions",
            )
        if len(self.lines) > MAX_LINES:
            raise ValidationError("lines", f"an invoice has at most {MAX_LINES} lines")
        if any(line.tax_rate is not None for line in self.lines):
            raise ValidationError("lines", "a template has no frozen tax rates")
        object.__setattr__(
            self, "subject", clean_text(self.subject, "subject", max_length=MAX_SUBJECT)
        )
        object.__setattr__(
            self, "reference", clean_text(self.reference, "reference", max_length=MAX_REFERENCE)
        )
        for name in ("intro_text", "payment_text", "closing_text"):
            object.__setattr__(
                self, name, clean_multiline(getattr(self, name), name, max_length=MAX_TEXT)
            )


@dataclass(frozen=True, slots=True)
class RecurringPlan:
    id: UUID
    name: str
    customer_id: UUID
    interval: Interval
    start_date: date
    """The day of the first invoice; every later one is counted from it."""
    next_date: date
    action: PlanAction
    template: InvoiceTemplate
    created_at: datetime
    end_date: date | None = None
    """No invoice after this day; None: until stopped."""
    service_period: bool = True
    """Put the period an invoice covers on it as service period."""
    active: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "name", clean_text(self.name, "name", max_length=MAX_NAME, required=True)
        )
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValidationError("end_date", "the plan ends before it starts")
        if self.next_date < self.start_date:
            raise ValidationError("next_date", "the next invoice is before the first one")

    @classmethod
    def new(  # noqa: PLR0913 - the parts of a plan
        cls,
        plan_id: UUID,
        *,
        name: str,
        customer_id: UUID,
        interval: Interval,
        start_date: date,
        action: PlanAction,
        template: InvoiceTemplate,
        today: date,
        now: datetime,
        end_date: date | None = None,
        service_period: bool = True,
    ) -> RecurringPlan:
        if start_date < today:
            raise ValidationError(
                "start_date", "the first invoice cannot be in the past", code="plan_start_in_past"
            )
        return cls(
            id=plan_id,
            name=name,
            customer_id=customer_id,
            interval=interval,
            start_date=start_date,
            next_date=start_date,
            action=action,
            template=template,
            created_at=now,
            end_date=end_date,
            service_period=service_period,
        )

    def change(  # noqa: PLR0913 - the parts of a plan
        self,
        *,
        name: str,
        customer_id: UUID,
        interval: Interval,
        start_date: date,
        action: PlanAction,
        template: InvoiceTemplate,
        today: date,
        end_date: date | None = None,
        service_period: bool = True,
    ) -> RecurringPlan:
        """Change the plan; a new first day or interval starts the counting anew."""
        restart = (start_date, interval) != (self.start_date, self.interval)
        if restart and start_date < today:
            raise ValidationError(
                "start_date", "the first invoice cannot be in the past", code="plan_start_in_past"
            )
        return replace(
            self,
            name=name,
            customer_id=customer_id,
            interval=interval,
            start_date=start_date,
            next_date=start_date if restart else self.next_date,
            action=action,
            template=template,
            end_date=end_date,
            service_period=service_period,
        )

    @property
    def finished(self) -> bool:
        """No invoice is left: the next day lies after the end."""
        return self.end_date is not None and self.next_date > self.end_date

    def is_due(self, today: date) -> bool:
        return self.active and not self.finished and self.next_date <= today

    def period(self) -> tuple[date, date]:
        """Return the period the next invoice covers: its day up to the day before the following.

        The last period ends with the plan.
        """
        last = self.following() - timedelta(days=1)
        if self.end_date is not None:
            last = min(last, self.end_date)
        return self.next_date, last

    def following(self) -> date:
        """Return the day of the invoice after the next one."""
        done = (self.next_date.year - self.start_date.year) * 12 + (
            self.next_date.month - self.start_date.month
        )
        return add_months(self.start_date, done + self.interval.months)

    def advance(self) -> RecurringPlan:
        """Move on to the next invoice once this one is written."""
        if self.finished:
            raise InvalidStateError("the plan has no invoice left")
        return replace(self, next_date=self.following())

    def pause(self) -> RecurringPlan:
        return replace(self, active=False)

    def resume(self, today: date) -> RecurringPlan:
        """Continue; invoices missed while paused are skipped, not written afterwards."""
        if self.active:
            # A running plan catches up missed periods itself; resuming would skip them.
            raise InvalidStateError("the plan is not paused", code="plan_not_paused")
        plan = self
        while plan.next_date < today and not plan.finished:
            plan = plan.advance()
        return replace(plan, active=True)


class RunOutcome(StrEnum):
    DRAFT = "draft"
    """A draft was created (as planned, or because issuing failed)."""
    ISSUED = "issued"
    SENT = "sent"
    FAILED = "failed"
    """Nothing was created; the message says why."""


@dataclass(frozen=True, slots=True)
class PlanRun:
    """One invoice of a plan: when, for which period, with which result."""

    plan_id: UUID
    period_start: date
    at: datetime
    outcome: RunOutcome
    document_id: UUID | None = None
    code: str = ""
    """The error code of what went wrong (e.g. "mail_auth_failed"); empty when all went well."""
    message: str = ""
    """The error's own words, e.g. the mail server's answer."""
