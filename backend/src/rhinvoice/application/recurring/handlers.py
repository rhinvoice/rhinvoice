"""Use cases of recurring invoices: the plans, and the run that writes their invoices."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Final

from rhinvoice.application.document.handlers import DraftInput, LineInput, chosen_account
from rhinvoice.application.errors import NotFoundError
from rhinvoice.application.mail.handlers import SendMail
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import Discount, DiscountKind
from rhinvoice.domain.recurring.plan import (
    MAX_CATCH_UP,
    InvoiceTemplate,
    PlanAction,
    PlanRun,
    RecurringPlan,
    RunOutcome,
)
from rhinvoice.domain.shared.errors import DomainError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import parse_decimal

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import date
    from uuid import UUID

    from rhinvoice.application.document.handlers import DocumentHandlers
    from rhinvoice.application.document.printing import PrintHandlers
    from rhinvoice.application.mail.handlers import MailHandlers
    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.document.lines import DocumentLine
    from rhinvoice.domain.recurring.plan import Interval
    from rhinvoice.domain.shared.clock import Clock
    from rhinvoice.domain.shared.money import Money

logger = logging.getLogger(__name__)


class WrittenBefore(Enum):
    """The period of a claim had its invoice already."""

    WRITTEN_BEFORE = "written before"


WRITTEN_BEFORE: Final = WrittenBefore.WRITTEN_BEFORE

RECENT_RUNS = 12
NO_CUSTOMER_EMAIL = "customer_email_missing"


@dataclass(frozen=True, slots=True)
class SavePlan:
    name: str
    customer_id: UUID
    interval: Interval
    start_date: date
    action: PlanAction
    template: DraftInput
    """The invoice's content; its customer, dates and tax choice are not used."""
    end_date: date | None = None
    service_period: bool = True


@dataclass(frozen=True, slots=True)
class PlanView:
    plan: RecurringPlan
    customer_name: str
    customer_archived: bool
    """The customer was archived; the plan still invoices them until it is paused."""
    total: Money | None
    """The total of the next invoice at today's rates; None when it cannot be calculated."""
    runs: tuple[PlanRun, ...]
    """The latest invoices, newest first."""


@dataclass(frozen=True, slots=True)
class RecurringHandlers:
    uow: UnitOfWorkFactory
    clock: Clock
    documents: DocumentHandlers
    printing: PrintHandlers
    mail: MailHandlers

    # --- Plans ----------------------------------------------------------------------

    def plans(self) -> list[PlanView]:
        with self.uow() as uow:
            plans = uow.recurring.all()
            runs = uow.recurring.runs([plan.id for plan in plans], limit=1)
        return [self._view(plan, runs.get(plan.id, [])) for plan in plans]

    def get(self, plan_id: UUID) -> PlanView:
        with self.uow() as uow:
            plan = _require(uow, plan_id)
            runs = uow.recurring.runs([plan_id], limit=RECENT_RUNS)
        return self._view(plan, runs.get(plan_id, []))

    def create(self, command: SavePlan) -> PlanView:
        with self.uow() as uow:
            _require_customer(uow, command.customer_id)
            _check_account(uow, command.template)
            plan = RecurringPlan.new(
                new_id(),
                name=command.name,
                customer_id=command.customer_id,
                interval=command.interval,
                start_date=command.start_date,
                action=command.action,
                template=to_template(command.template),
                today=self.clock.today(),
                now=self.clock.now(),
                end_date=command.end_date,
                service_period=command.service_period,
            )
            uow.recurring.add(plan)
            uow.commit()
        return self._view(plan, [])

    def update(self, plan_id: UUID, command: SavePlan) -> PlanView:
        with self.uow() as uow:
            _require_customer(uow, command.customer_id)
            _check_account(uow, command.template)
            plan = _require(uow, plan_id, for_update=True).change(
                name=command.name,
                customer_id=command.customer_id,
                interval=command.interval,
                start_date=command.start_date,
                action=command.action,
                template=to_template(command.template),
                today=self.clock.today(),
                end_date=command.end_date,
                service_period=command.service_period,
            )
            uow.recurring.update(plan)
            uow.commit()
        return self.get(plan_id)

    def pause(self, plan_id: UUID) -> PlanView:
        return self._change(plan_id, RecurringPlan.pause)

    def resume(self, plan_id: UUID) -> PlanView:
        return self._change(plan_id, lambda plan: plan.resume(self.clock.today()))

    def delete(self, plan_id: UUID) -> None:
        """Remove the plan; the invoices it wrote stay as they are."""
        with self.uow() as uow:
            _require(uow, plan_id)
            uow.recurring.delete(plan_id)
            uow.commit()

    # --- The run ----------------------------------------------------------------------

    def run_due(self) -> list[PlanRun]:
        """Write the invoices that are due, each period once, also after a downtime."""
        today = self.clock.today()
        with self.uow() as uow:
            due = uow.recurring.due(today)
        written: list[PlanRun] = []
        for plan_id in due:
            try:
                written.extend(self._catch_up(plan_id, today))
            except Exception:
                logger.exception("recurring invoices of plan %s failed", plan_id)
        problems = [run for run in written if run.code]
        for run in problems:
            logger.warning(
                "recurring invoice of plan %s for %s: %s (%s)",
                run.plan_id,
                run.period_start.isoformat(),
                run.code,
                run.message,
            )
        if written:
            logger.info(
                "recurring invoices: %d written, %d with problems", len(written), len(problems)
            )
        return written

    def _catch_up(self, plan_id: UUID, today: date) -> list[PlanRun]:
        """Write the due periods of one plan, at most MAX_CATCH_UP at a time."""
        written: list[PlanRun] = []
        for _ in range(MAX_CATCH_UP):
            claimed = self._claim(plan_id, today)
            if claimed is None:
                break
            if claimed is WRITTEN_BEFORE:
                continue
            plan, run = claimed
            written.append(self._run(plan, run))
        return written

    def _run(self, plan: RecurringPlan, run: PlanRun) -> PlanRun:
        """Write one period; an unexpected failure is kept on the run, with what was done."""
        try:
            finished = self._write(plan, run)
        except Exception as error:
            logger.exception("recurring invoice of plan %s failed", plan.id)
            finished = replace(
                self._stored(run),
                code="unexpected_error",
                message=str(error) or type(error).__name__,
            )
        self._finish(finished)
        return finished

    def _finish(self, run: PlanRun) -> None:
        with self.uow() as uow:
            uow.recurring.finish(run)
            uow.commit()

    def _stored(self, run: PlanRun) -> PlanRun:
        """Return the run as last saved (it names the invoice once it was created)."""
        with self.uow() as uow:
            runs = uow.recurring.runs([run.plan_id], limit=MAX_CATCH_UP * 2).get(run.plan_id, [])
        return next((known for known in runs if known.period_start == run.period_start), run)

    def _claim(
        self, plan_id: UUID, today: date
    ) -> tuple[RecurringPlan, PlanRun] | WrittenBefore | None:
        """Take the next period of a due plan and move the plan on, in one transaction.

        A period written before (e.g. the first day again after a changed interval) is
        not written twice: the plan just moves on.
        """
        with self.uow() as uow:
            plan = uow.recurring.get(plan_id, for_update=True)
            if plan is None or not plan.is_due(today):
                return None
            run = PlanRun(
                plan_id=plan.id,
                period_start=plan.next_date,
                at=self.clock.now(),
                outcome=RunOutcome.FAILED,
                code="interrupted",
                message="the run stopped before the invoice was written",
            )
            claimed = uow.recurring.claim(run)
            uow.recurring.update(plan.advance())
            uow.commit()
        return (plan, run) if claimed else WRITTEN_BEFORE

    def _write(self, plan: RecurringPlan, run: PlanRun) -> PlanRun:
        """Create, issue and send the invoice of one period, as far as the plan says."""
        first, last = plan.period()
        draft = replace(
            self._draft(plan),
            service_from=first if plan.service_period else None,
            service_to=last if plan.service_period else None,
        )
        try:
            invoice = self.documents.create(DocumentType.INVOICE, draft).document.id
        except DomainError as error:
            return _failed(run, error)
        # Kept right away: should anything fail from here on, the run still names its invoice.
        self._finish(replace(run, outcome=RunOutcome.DRAFT, document_id=invoice))
        done = replace(run, outcome=RunOutcome.DRAFT, document_id=invoice, code="", message="")
        if plan.action is PlanAction.DRAFT:
            return done
        try:
            self.documents.issue(invoice)
        except DomainError as error:
            # The draft stays: the person sees why it was not issued and can fix it.
            return _failed(done, error)
        # Freezes the PDF now; without the PDF service it happens on the first download.
        self.printing.archive(invoice)
        done = replace(done, outcome=RunOutcome.ISSUED)
        if plan.action is PlanAction.ISSUE:
            return done
        return self._send(done, invoice)

    def _send(self, run: PlanRun, invoice: UUID) -> PlanRun:
        try:
            draft = self.mail.document_draft(invoice)
            if not draft.to:
                return replace(
                    run,
                    code=NO_CUSTOMER_EMAIL,
                    message="the customer has no e-mail address; the invoice was not sent",
                )
            self.mail.send_document(
                invoice, SendMail(to=draft.to, subject=draft.subject, body=draft.body)
            )
        except DomainError as error:
            return _failed(run, error)
        return replace(run, outcome=RunOutcome.SENT)

    # --- Helpers ----------------------------------------------------------------------

    def _change(self, plan_id: UUID, change: Callable[[RecurringPlan], RecurringPlan]) -> PlanView:
        with self.uow() as uow:
            plan = change(_require(uow, plan_id, for_update=True))
            uow.recurring.update(plan)
            uow.commit()
        return self.get(plan_id)

    def _draft(self, plan: RecurringPlan) -> DraftInput:
        """Return the plan's invoice; an account deleted since gives way to the default."""
        draft = plan_draft(plan)
        if draft.bank_account_id is None:
            return draft
        with self.uow() as uow:
            account = uow.bank_accounts.get(draft.bank_account_id)
        if account is None or account.currency is not draft.currency:
            return replace(draft, bank_account_id=None)
        return draft

    def _view(self, plan: RecurringPlan, runs: Sequence[PlanRun]) -> PlanView:
        with self.uow() as uow:
            customer = uow.customers.get(plan.customer_id)
        try:
            draft = self._draft(plan)
            total = self.documents.preview(DocumentType.INVOICE, draft).view.totals.total
        except DomainError:
            total = None  # e.g. a tax category the country no longer has
        return PlanView(
            plan=plan,
            customer_name="" if customer is None else customer.display_name,
            customer_archived=customer is not None and customer.archived,
            total=total,
            runs=tuple(runs),
        )


def to_template(draft: DraftInput) -> InvoiceTemplate:
    """Turn the editor's content into a plan's template (the lines are checked here)."""
    discount = (
        None
        if draft.discount_value is None
        else Discount(draft.discount_kind, parse_decimal(draft.discount_value, "discount"))
    )
    if draft.currency is None:
        raise ValidationError("currency", "a plan names its currency")
    return InvoiceTemplate(
        currency=draft.currency,
        price_mode=draft.price_mode,
        lines=tuple(line.to_domain(index) for index, line in enumerate(draft.lines)),
        language=draft.language,
        discount=discount,
        subject=draft.subject,
        reference=draft.reference,
        intro_text=draft.intro_text,
        payment_text=draft.payment_text,
        closing_text=draft.closing_text,
        bank_account_id=draft.bank_account_id,
    )


def plan_draft(plan: RecurringPlan) -> DraftInput:
    """Return the invoice the plan writes, as the editor would send it."""
    template = plan.template
    discount = template.discount
    return DraftInput(
        customer_id=plan.customer_id,
        currency=template.currency,
        language=template.language,
        price_mode=template.price_mode,
        lines=tuple(_line_input(line) for line in template.lines),
        discount_kind=DiscountKind.PERCENT if discount is None else discount.kind,
        discount_value=None if discount is None else str(discount.value),
        subject=template.subject,
        reference=template.reference,
        intro_text=template.intro_text,
        payment_text=template.payment_text,
        closing_text=template.closing_text,
        bank_account_id=template.bank_account_id,
    )


def _line_input(line: DocumentLine) -> LineInput:
    return LineInput(
        kind=line.kind,
        description=line.description,
        details=line.details,
        quantity=str(line.quantity),
        unit=None if line.unit is None else line.unit.code,
        unit_price=str(line.unit_price),
        discount_percent=str(line.discount_percent),
        tax_category=line.tax_category,
        supply=line.supply,
        article_id=line.article_id,
    )


def _failed(run: PlanRun, error: DomainError) -> PlanRun:
    """Keep what the run got to (outcome, invoice) with the reason it stopped there."""
    return replace(run, code=error.code, message=error.message)


def _require(uow: UnitOfWork, plan_id: UUID, *, for_update: bool = False) -> RecurringPlan:
    plan = uow.recurring.get(plan_id, for_update=for_update)
    if plan is None:
        raise NotFoundError("plan not found")
    return plan


def _check_account(uow: UnitOfWork, template: DraftInput) -> None:
    """Check a plan's account like a draft's: it exists and is in the plan's currency."""
    if template.currency is not None:
        chosen_account(uow, template.bank_account_id, template.currency)


def _require_customer(uow: UnitOfWork, customer_id: UUID) -> None:
    if uow.customers.get(customer_id) is None:
        raise ValidationError("customer_id", "the customer does not exist")
