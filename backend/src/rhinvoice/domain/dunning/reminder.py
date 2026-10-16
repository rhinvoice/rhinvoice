"""Payment reminders for overdue invoices: a payment reminder, then two dunning letters.

Each level becomes due a number of days after the previous deadline (the
invoice's due date for the first) and sets a new deadline. A level may be written
early only on purpose (``early``), and only the level the person saw: a second
click must not write the next one. Each level may add a fee (none by default: a
fee needs an agreement or proof of the costs, see OPEN_QUESTIONS 16); dunning
fees are damages, not a supply, and carry no VAT (CH: MWSTG Art. 18 Abs. 2
lit. i; DE: UStAE 1.3 Abs. 6; AT: see OPEN_QUESTIONS). The text is kept with the
reminder, so its letter can be printed again as it was sent.
"""

# ruff: noqa: RUF001 - French and Italian elide with the typographic apostrophe.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from rhinvoice.domain.document.document import DisplayStatus, DocumentType
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Money
from rhinvoice.domain.shared.text import clean_multiline

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date, datetime
    from uuid import UUID

    from rhinvoice.domain.document.document import Document

LEVELS = (1, 2, 3)
MAX_DAYS = 365
MAX_FEE = Decimal(1000)
MAX_TEXT = 2000
FEE_STEP = Decimal("0.05")
"""Fees fit the Swiss 5-centime rounding of the payment codes."""


@dataclass(frozen=True, slots=True)
class DunningLevel:
    level: int
    days_after_due: int
    """Days after the previous deadline when this level becomes due."""
    payment_days: int
    """The new deadline, counted from the day of the reminder."""
    fee: Decimal
    """In the invoice's currency; 0 for none."""
    text_de: str
    text_en: str
    text_fr: str
    text_it: str

    def __post_init__(self) -> None:
        if self.level not in LEVELS:
            raise ValidationError("level", f"the level must be one of {LEVELS}")
        if not 0 <= self.days_after_due <= MAX_DAYS:
            raise ValidationError("days_after_due", f"must be between 0 and {MAX_DAYS} days")
        if not 1 <= self.payment_days <= MAX_DAYS:
            raise ValidationError("payment_days", f"must be between 1 and {MAX_DAYS} days")
        if not Decimal(0) <= self.fee <= MAX_FEE or self.fee % FEE_STEP:
            raise ValidationError(
                "fee", f"the fee must be between 0 and {MAX_FEE} in steps of {FEE_STEP}"
            )
        for name in ("text_de", "text_en", "text_fr", "text_it"):
            object.__setattr__(
                self, name, clean_multiline(getattr(self, name), name, max_length=MAX_TEXT)
            )

    def text(self, language: Language) -> str:
        """Return the level's text in ``language``."""
        return {
            Language.DE: self.text_de,
            Language.EN: self.text_en,
            Language.FR: self.text_fr,
            Language.IT: self.text_it,
        }[language]


@dataclass(frozen=True, slots=True)
class Reminder:
    id: UUID
    invoice_id: UUID
    level: int
    issued_on: date
    due_date: date
    open_amount: Money
    """What was still open on the invoice when the reminder was written."""
    fee: Money
    created_at: datetime
    text: str
    """The level's text in the invoice's language, as it was when writing."""

    @property
    def total(self) -> Money:
        return self.open_amount + self.fee


@dataclass(frozen=True, slots=True)
class NextReminder:
    level: int
    due_on: date
    """The day this level becomes due (it may be written earlier on purpose)."""
    fee: Money
    deadline: date
    """The new deadline if the reminder is written today."""

    def is_due(self, today: date) -> bool:
        return today >= self.due_on


@dataclass(frozen=True, slots=True)
class Dunning:
    """The reminders of one invoice and what comes next."""

    invoice: Document
    reminders: Sequence[Reminder] = field(default_factory=tuple)

    def next(self, levels: Sequence[DunningLevel], today: date) -> NextReminder | None:
        """Return the next level of an overdue invoice, or None (not overdue, all sent)."""
        invoice = self.invoice
        if (
            invoice.type is not DocumentType.INVOICE
            or invoice.display_status(today) is not DisplayStatus.OVERDUE
            or invoice.content.due_date is None
        ):
            return None
        last = max(self.reminders, key=lambda reminder: reminder.level, default=None)
        level = 1 if last is None else last.level + 1
        if level not in LEVELS:
            return None
        settings = _level(levels, level)
        previous = invoice.content.due_date if last is None else last.due_date
        return NextReminder(
            level=level,
            due_on=previous + timedelta(days=settings.days_after_due),
            fee=Money(settings.fee, invoice.content.currency),
            deadline=today + timedelta(days=settings.payment_days),
        )

    def remind(  # noqa: PLR0913 - the request and the time, all keyword-only
        self,
        levels: Sequence[DunningLevel],
        *,
        level: int,
        early: bool,
        reminder_id: UUID,
        today: date,
        now: datetime,
    ) -> Reminder:
        """Write the next reminder: the expected ``level``, before it is due only ``early``."""
        upcoming = self.next(levels, today)
        if upcoming is None:
            raise InvalidStateError(
                "only overdue invoices get a reminder, at most three", code="not_remindable"
            )
        if upcoming.level != level:
            raise InvalidStateError(
                f"the next reminder is level {upcoming.level}, not {level}",
                code="reminder_level_changed",
            )
        if not early and not upcoming.is_due(today):
            raise InvalidStateError(
                f"level {level} is due on {upcoming.due_on}", code="reminder_not_due"
            )
        settings = _level(levels, level)
        return Reminder(
            id=reminder_id,
            invoice_id=self.invoice.id,
            level=level,
            issued_on=today,
            due_date=upcoming.deadline,
            open_amount=self.invoice.open_amount(),
            fee=upcoming.fee,
            created_at=now,
            text=settings.text(self.invoice.content.language),
        )


def _level(levels: Sequence[DunningLevel], level: int) -> DunningLevel:
    for candidate in levels:
        if candidate.level == level:
            return candidate
    raise ValidationError("level", f"level {level} is not configured")


FRENCH_TEXTS = {
    1: (
        "Sans doute cela vous a-t-il échappé : la facture suivante est encore ouverte. Nous "
        "vous prions de verser le montant d’ici au {faellig}. Si vous avez déjà effectué le "
        "paiement, veuillez considérer ce courrier comme nul et non avenu."
    ),
    2: (
        "Malgré notre rappel de paiement, la facture suivante n’est toujours pas payée. Nous "
        "vous prions de verser le montant ouvert d’ici au {faellig}."
    ),
    3: (
        "La facture suivante est encore ouverte malgré notre rappel de paiement et notre "
        "rappel. Nous vous prions de verser le montant d’ici au {faellig}. À défaut, nous "
        "devrons faire valoir notre créance par voie juridique sans autre avis."
    ),
}
"""The built-in French texts per level; also what the migration gives existing settings."""

ITALIAN_TEXTS = {
    1: (
        "Forse vi è sfuggito: la seguente fattura risulta ancora aperta. Vi preghiamo di "
        "versare l’importo entro il {faellig}. Se avete già effettuato il pagamento, vi "
        "preghiamo di non tenere conto di questa lettera."
    ),
    2: (
        "Nonostante il nostro promemoria di pagamento, la seguente fattura non è ancora stata "
        "pagata. Vi preghiamo di versare l’importo aperto entro il {faellig}."
    ),
    3: (
        "La seguente fattura risulta ancora aperta nonostante il promemoria e il sollecito. Vi "
        "preghiamo di versare l’importo entro il {faellig}. In caso contrario dovremo far "
        "valere il credito per via legale senza ulteriore preavviso."
    ),
}
"""The built-in Italian texts per level; also what the migration gives existing settings."""

DEFAULT_LEVELS = (
    DunningLevel(
        level=1,
        days_after_due=7,
        payment_days=10,
        fee=Decimal("0.00"),
        text_de=(
            "Sicher ist es Ihrer Aufmerksamkeit entgangen: Die folgende Rechnung ist noch offen. "
            "Wir bitten Sie, den Betrag bis {faellig} zu überweisen. Falls Sie die Zahlung "
            "bereits veranlasst haben, betrachten Sie dieses Schreiben bitte als gegenstandslos."
        ),
        text_en=(
            "Perhaps it escaped your attention: the following invoice is still open. Please "
            "transfer the amount by {faellig}. If you have already paid, please disregard "
            "this letter."
        ),
        text_fr=FRENCH_TEXTS[1],
        text_it=ITALIAN_TEXTS[1],
    ),
    DunningLevel(
        level=2,
        days_after_due=7,
        payment_days=10,
        fee=Decimal("0.00"),
        text_de=(
            "Trotz unserer Zahlungserinnerung ist die folgende Rechnung noch nicht bezahlt. "
            "Wir bitten Sie, den offenen Betrag bis {faellig} zu überweisen."
        ),
        text_en=(
            "Despite our reminder, the following invoice has not been paid yet. Please "
            "transfer the open amount by {faellig}."
        ),
        text_fr=FRENCH_TEXTS[2],
        text_it=ITALIAN_TEXTS[2],
    ),
    DunningLevel(
        level=3,
        days_after_due=7,
        payment_days=7,
        fee=Decimal("0.00"),
        text_de=(
            "Die folgende Rechnung ist trotz Zahlungserinnerung und Mahnung noch offen. "
            "Bitte überweisen "
            "Sie den Betrag bis {faellig}. Andernfalls müssen wir die Forderung ohne weitere "
            "Ankündigung rechtlich geltend machen."
        ),
        text_en=(
            "The following invoice is still open despite our reminders. Please transfer the "
            "amount by {faellig}. Otherwise we will have to enforce the claim without "
            "further notice."
        ),
        text_fr=FRENCH_TEXTS[3],
        text_it=ITALIAN_TEXTS[3],
    ),
)
