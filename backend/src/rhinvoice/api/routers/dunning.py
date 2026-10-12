from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Response, status
from fastapi.responses import HTMLResponse
from pydantic import Field

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.routers.documents import HTML_PAGE, PDF_FILE, SummaryResponse, amount
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.dunning.handlers import DunningItem
from rhinvoice.domain.dunning.reminder import MAX_DAYS, MAX_FEE, MAX_TEXT, DunningLevel, Reminder
from rhinvoice.infrastructure.rendering.pdf import file_name, reminder_title

router = APIRouter(prefix="/api", tags=["dunning"], responses=ERROR_RESPONSES)

Level = Annotated[int, Field(ge=1, le=3)]
Days = Annotated[int, Field(ge=0, le=MAX_DAYS)]


class ReminderResponse(ApiModel):
    id: UUID
    invoice_id: UUID
    level: int
    issued_on: date
    due_date: date
    currency: str
    open_amount: str
    fee: str
    total: str
    created_at: datetime

    @classmethod
    def of(cls, reminder: Reminder) -> Self:
        return cls(
            id=reminder.id,
            invoice_id=reminder.invoice_id,
            level=reminder.level,
            issued_on=reminder.issued_on,
            due_date=reminder.due_date,
            currency=reminder.open_amount.currency.value,
            open_amount=amount(reminder.open_amount),
            fee=amount(reminder.fee),
            total=amount(reminder.total),
            created_at=reminder.created_at,
        )


class NextReminderResponse(ApiModel):
    level: int
    due_on: date
    due: bool
    """The level is due today or was due before (otherwise it is written only ``early``)."""
    fee: str
    deadline: date
    """The new deadline if the reminder is written today."""


class DunningItemResponse(ApiModel):
    invoice: SummaryResponse
    days_overdue: int
    reminders: list[ReminderResponse]
    next: NextReminderResponse | None
    """None when all three reminders were written."""

    @classmethod
    def of(cls, item: DunningItem, today: date) -> Self:
        upcoming = item.next
        due = item.invoice.due_date
        return cls(
            invoice=SummaryResponse.of(item.invoice),
            # Overdue invoices always have a due date before today.
            days_overdue=0 if due is None else (today - due).days,
            reminders=[ReminderResponse.of(reminder) for reminder in item.reminders],
            next=None
            if upcoming is None
            else NextReminderResponse(
                level=upcoming.level,
                due_on=upcoming.due_on,
                due=upcoming.is_due(today),
                fee=amount(upcoming.fee),
                deadline=upcoming.deadline,
            ),
        )


class WriteReminderRequest(ApiModel):
    level: Level
    """The level shown to the person: when another one was written meanwhile, 409."""
    early: bool = False
    """Write the level before it is due."""


class DunningLevelSchema(ApiModel):
    level: Level
    days_after_due: Days
    """Days after the previous deadline when this level becomes due."""
    payment_days: Annotated[int, Field(ge=1, le=MAX_DAYS)]
    """The new deadline, counted from the day of the reminder."""
    fee: Decimal = Field(ge=0, le=MAX_FEE, decimal_places=2)
    """In the invoice's currency."""
    text_de: str = Field(max_length=MAX_TEXT)
    text_en: str = Field(max_length=MAX_TEXT)

    @classmethod
    def of(cls, level: DunningLevel) -> Self:
        return cls(
            level=level.level,
            days_after_due=level.days_after_due,
            payment_days=level.payment_days,
            fee=level.fee,
            text_de=level.text_de,
            text_en=level.text_en,
        )

    def to_domain(self) -> DunningLevel:
        return DunningLevel(
            level=self.level,
            days_after_due=self.days_after_due,
            payment_days=self.payment_days,
            fee=self.fee.quantize(Decimal("0.01")),
            text_de=self.text_de,
            text_en=self.text_en,
        )


@router.get("/dunning")
def dunning_overview(_user: CurrentUser, container: ContainerDep) -> list[DunningItemResponse]:
    """Overdue invoices, longest overdue first, with their reminders and the next level."""
    today = container.clock.today()
    return [DunningItemResponse.of(item, today) for item in container.dunning.overview()]


@router.get("/dunning/levels")
def dunning_levels(_user: CurrentUser, container: ContainerDep) -> list[DunningLevelSchema]:
    return [DunningLevelSchema.of(level) for level in container.dunning.levels()]


@router.put("/dunning/levels")
def save_dunning_levels(
    body: Annotated[list[DunningLevelSchema], Field(min_length=3, max_length=3)],
    _user: CurrentUser,
    container: ContainerDep,
) -> list[DunningLevelSchema]:
    saved = container.dunning.save_levels([level.to_domain() for level in body])
    return [DunningLevelSchema.of(level) for level in saved]


@router.get("/documents/{document_id}/reminders")
def list_reminders(
    document_id: UUID, _user: CurrentUser, container: ContainerDep
) -> list[ReminderResponse]:
    return [ReminderResponse.of(reminder) for reminder in container.dunning.reminders(document_id)]


@router.post("/documents/{document_id}/reminders", status_code=status.HTTP_201_CREATED)
def write_reminder(
    document_id: UUID, body: WriteReminderRequest, _user: CurrentUser, container: ContainerDep
) -> ReminderResponse:
    """Write the next reminder of an overdue invoice.

    409 not_remindable (not overdue, all written), reminder_level_changed (another
    level is next) or reminder_not_due (before its day without ``early``).
    """
    reminder, _view = container.dunning.remind(document_id, level=body.level, early=body.early)
    return ReminderResponse.of(reminder)


@router.get("/reminders/{reminder_id}/html", response_class=HTMLResponse, responses=HTML_PAGE)
def reminder_html(reminder_id: UUID, _user: CurrentUser, container: ContainerDep) -> HTMLResponse:
    return HTMLResponse(container.printing.reminder_html(reminder_id))


@router.get("/reminders/{reminder_id}/pdf", response_class=Response, responses=PDF_FILE)
def reminder_pdf(
    reminder_id: UUID,
    _user: CurrentUser,
    container: ContainerDep,
    download: bool = False,  # noqa: FBT001, FBT002 - a query flag
) -> Response:
    """Return the reminder as PDF, shown in the browser or (``download``) saved as a file."""
    printed, content = container.printing.reminder_pdf(reminder_id)
    name = file_name(reminder_title(printed))
    fallback = name.encode("ascii", "replace").decode().replace("?", "_")
    disposition = "attachment" if download else "inline"
    headers = {
        "Content-Disposition": (
            f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"
        ),
        "Cache-Control": "no-store",
    }
    return Response(content=content, media_type="application/pdf", headers=headers)
