"""Recurring invoices: plans that write the same invoice every period (ADR 0016)."""

from datetime import date, datetime
from typing import Self
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import Field

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.routers.documents import LineRequest, amount
from rhinvoice.api.schemas import DECIMAL_PATTERN, ERROR_RESPONSES, ApiModel, text
from rhinvoice.application.document.handlers import DraftInput
from rhinvoice.application.recurring.handlers import PlanView, SavePlan, plan_draft
from rhinvoice.domain.document.document import MAX_LINES
from rhinvoice.domain.document.lines import DiscountKind, LineKind, PriceMode
from rhinvoice.domain.recurring.plan import (
    MAX_NAME,
    Interval,
    PlanAction,
    PlanRun,
    RecurringPlan,
    RunOutcome,
)
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply

router = APIRouter(prefix="/api", tags=["recurring"], responses=ERROR_RESPONSES)


class InvoiceTemplateRequest(ApiModel):
    """The invoice every period starts with."""

    currency: Currency
    language: Language | None = None
    price_mode: PriceMode = PriceMode.NET
    lines: list[LineRequest] = Field(default_factory=list[LineRequest], max_length=MAX_LINES)
    discount_kind: DiscountKind = DiscountKind.PERCENT
    discount_value: str | None = Field(default=None, pattern=DECIMAL_PATTERN)
    """None: the customer's default discount at the time of each invoice."""
    subject: str = text(200)
    reference: str = text(100)
    intro_text: str = text(4000)
    payment_text: str = text(4000)
    closing_text: str = text(4000)
    bank_account_id: UUID | None = None
    """None: the default account of the currency."""


class PlanRequest(ApiModel):
    name: str = text(MAX_NAME, required=True)
    customer_id: UUID
    interval: Interval
    start_date: date
    """The day of the first invoice (today or later)."""
    end_date: date | None = None
    action: PlanAction
    service_period: bool = True
    template: InvoiceTemplateRequest

    def to_command(self) -> SavePlan:
        template = self.template
        return SavePlan(
            name=self.name,
            customer_id=self.customer_id,
            interval=self.interval,
            start_date=self.start_date,
            end_date=self.end_date,
            action=self.action,
            service_period=self.service_period,
            template=DraftInput(
                customer_id=self.customer_id,
                currency=template.currency,
                language=template.language,
                price_mode=template.price_mode,
                lines=tuple(line.to_input() for line in template.lines),
                discount_kind=template.discount_kind,
                discount_value=template.discount_value,
                subject=template.subject,
                reference=template.reference,
                intro_text=template.intro_text,
                payment_text=template.payment_text,
                closing_text=template.closing_text,
                bank_account_id=template.bank_account_id,
            ),
        )


class InvoiceTemplateLineResponse(ApiModel):
    kind: LineKind
    description: str
    details: str
    quantity: str
    unit: str | None
    unit_price: str
    discount_percent: str
    tax_category: TaxCategory
    supply: Supply
    article_id: UUID | None


class InvoiceTemplateResponse(ApiModel):
    currency: Currency
    language: Language | None
    price_mode: PriceMode
    lines: list[InvoiceTemplateLineResponse]
    discount_kind: DiscountKind
    discount_value: str | None
    subject: str
    reference: str
    intro_text: str
    payment_text: str
    closing_text: str
    bank_account_id: UUID | None

    @classmethod
    def of(cls, plan: RecurringPlan) -> Self:
        draft = plan_draft(plan)
        return cls(
            currency=plan.template.currency,
            language=draft.language,
            price_mode=draft.price_mode,
            lines=[
                InvoiceTemplateLineResponse(
                    kind=line.kind,
                    description=line.description,
                    details=line.details,
                    quantity=line.quantity,
                    unit=line.unit,
                    unit_price=line.unit_price,
                    discount_percent=line.discount_percent,
                    tax_category=line.tax_category,
                    supply=line.supply,
                    article_id=line.article_id,
                )
                for line in draft.lines
            ],
            discount_kind=draft.discount_kind,
            discount_value=draft.discount_value,
            subject=draft.subject,
            reference=draft.reference,
            intro_text=draft.intro_text,
            payment_text=draft.payment_text,
            closing_text=draft.closing_text,
            bank_account_id=draft.bank_account_id,
        )


class RunResponse(ApiModel):
    period_start: date
    at: datetime
    outcome: RunOutcome
    document_id: UUID | None
    code: str
    """The error code of what went wrong; empty when all went as planned."""
    message: str

    @classmethod
    def of(cls, run: PlanRun) -> Self:
        return cls(
            period_start=run.period_start,
            at=run.at,
            outcome=run.outcome,
            document_id=run.document_id,
            code=run.code,
            message=run.message,
        )


class PlanResponse(ApiModel):
    id: UUID
    name: str
    customer_id: UUID
    customer_name: str
    customer_archived: bool
    interval: Interval
    start_date: date
    next_date: date
    end_date: date | None
    action: PlanAction
    service_period: bool
    active: bool
    finished: bool
    """No invoice left: the next one would be after the end."""
    period_end: date
    """The last day of the period the next invoice covers (it starts on ``next_date``)."""
    total: str | None
    """The total of the next invoice at today's rates and prices of the template."""
    template: InvoiceTemplateResponse
    runs: list[RunResponse]
    """The latest invoices, newest first (in the list: the last one only)."""

    @classmethod
    def of(cls, view: PlanView) -> Self:
        plan = view.plan
        return cls(
            id=plan.id,
            name=plan.name,
            customer_id=plan.customer_id,
            customer_name=view.customer_name,
            customer_archived=view.customer_archived,
            interval=plan.interval,
            start_date=plan.start_date,
            next_date=plan.next_date,
            end_date=plan.end_date,
            action=plan.action,
            service_period=plan.service_period,
            active=plan.active,
            finished=plan.finished,
            period_end=plan.period()[1],
            total=None if view.total is None else amount(view.total),
            template=InvoiceTemplateResponse.of(plan),
            runs=[RunResponse.of(run) for run in view.runs],
        )


@router.get("/recurring")
def list_plans(_user: CurrentUser, container: ContainerDep) -> list[PlanResponse]:
    return [PlanResponse.of(view) for view in container.recurring.plans()]


@router.post("/recurring", status_code=status.HTTP_201_CREATED)
def create_plan(body: PlanRequest, _user: CurrentUser, container: ContainerDep) -> PlanResponse:
    return PlanResponse.of(container.recurring.create(body.to_command()))


@router.get("/recurring/{plan_id}")
def get_plan(plan_id: UUID, _user: CurrentUser, container: ContainerDep) -> PlanResponse:
    return PlanResponse.of(container.recurring.get(plan_id))


@router.put("/recurring/{plan_id}")
def update_plan(
    plan_id: UUID, body: PlanRequest, _user: CurrentUser, container: ContainerDep
) -> PlanResponse:
    """Change the plan; a new first day or interval starts the counting anew."""
    return PlanResponse.of(container.recurring.update(plan_id, body.to_command()))


@router.post("/recurring/{plan_id}/pause")
def pause_plan(plan_id: UUID, _user: CurrentUser, container: ContainerDep) -> PlanResponse:
    return PlanResponse.of(container.recurring.pause(plan_id))


@router.post("/recurring/{plan_id}/resume")
def resume_plan(plan_id: UUID, _user: CurrentUser, container: ContainerDep) -> PlanResponse:
    """Continue; invoices missed while paused are skipped."""
    return PlanResponse.of(container.recurring.resume(plan_id))


@router.delete("/recurring/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: UUID, _user: CurrentUser, container: ContainerDep) -> None:
    """Remove the plan; the invoices it wrote stay."""
    container.recurring.delete(plan_id)
