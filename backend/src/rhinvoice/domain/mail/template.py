"""Subject and text of the mails that carry documents, per kind and language.

The built-in wording is the default; the company can replace it per kind and
language in the settings. Placeholders are those of the document texts
(``{nummer}``, ``{faellig}`` …); in reminders ``{faellig}`` is the new deadline and
``{betrag}`` the amount asked for. The greeting follows the company's country
(Swiss German writes "Grüsse").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.text import clean_multiline, clean_text
from rhinvoice.domain.text.template import Placeholder, unknown_placeholders

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rhinvoice.domain.document.document import DocumentType
    from rhinvoice.domain.shared.country import Country

MAX_SUBJECT = 200
MAX_BODY = 5000


class MailKind(StrEnum):
    INVOICE = "invoice"
    QUOTE = "quote"
    CANCELLATION = "cancellation"
    REMINDER_1 = "reminder_1"
    """Payment reminder."""
    REMINDER_2 = "reminder_2"
    """First dunning letter."""
    REMINDER_3 = "reminder_3"
    """Second (final) dunning letter."""

    @classmethod
    def of_document(cls, document_type: DocumentType) -> MailKind:
        return cls(document_type.value)

    @classmethod
    def of_reminder(cls, level: int) -> MailKind:
        return cls(f"reminder_{level}")


@dataclass(frozen=True, slots=True)
class MailTemplate:
    kind: MailKind
    language: Language
    subject: str
    body: str

    def __post_init__(self) -> None:
        subject = clean_text(self.subject, "subject", max_length=MAX_SUBJECT, required=True)
        body = clean_multiline(self.body, "body", max_length=MAX_BODY)
        if not body:
            raise ValidationError("body", "body is required")
        for field, text in (("subject", subject), ("body", body)):
            unknown = unknown_placeholders(text)
            if unknown:
                allowed = ", ".join(f"{{{placeholder.value}}}" for placeholder in Placeholder)
                raise ValidationError(
                    field,
                    f"unknown placeholder {{{unknown[0]}}}; available are {allowed}",
                    code="unknown_placeholder",
                )
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "body", body)


_SUBJECTS: Mapping[Language, Mapping[MailKind, str]] = {
    Language.DE: {
        MailKind.INVOICE: "Rechnung {nummer}",
        MailKind.QUOTE: "Angebot {nummer}",
        MailKind.CANCELLATION: "Stornorechnung {nummer}",
        MailKind.REMINDER_1: "Zahlungserinnerung zur Rechnung {nummer}",
        MailKind.REMINDER_2: "1. Mahnung zur Rechnung {nummer}",
        MailKind.REMINDER_3: "2. Mahnung zur Rechnung {nummer}",
    },
    Language.EN: {
        MailKind.INVOICE: "Invoice {nummer}",
        MailKind.QUOTE: "Quote {nummer}",
        MailKind.CANCELLATION: "Credit note {nummer}",
        MailKind.REMINDER_1: "Payment reminder for invoice {nummer}",
        MailKind.REMINDER_2: "Second reminder for invoice {nummer}",
        MailKind.REMINDER_3: "Final reminder for invoice {nummer}",
    },
}
_TEXTS: Mapping[Language, Mapping[MailKind, str]] = {
    Language.DE: {
        MailKind.INVOICE: (
            "Im Anhang erhalten Sie unsere Rechnung {nummer} über {waehrung} {betrag},"
            " zahlbar bis {faellig}."
        ),
        MailKind.QUOTE: (
            "Im Anhang erhalten Sie unser Angebot {nummer} über {waehrung} {betrag}."
            " Es ist gültig bis {faellig}. Wir freuen uns auf Ihren Auftrag."
        ),
        MailKind.CANCELLATION: "Im Anhang erhalten Sie die Stornorechnung {nummer}.",
        MailKind.REMINDER_1: (
            "Unsere Rechnung {nummer} ist noch offen. Vielleicht ist sie Ihnen entgangen."
            " Bitte überweisen Sie {waehrung} {betrag} bis {faellig}. Die Zahlungserinnerung"
            " finden Sie im Anhang. Sollten Sie bereits bezahlt haben, betrachten Sie diese"
            " Nachricht bitte als gegenstandslos."
        ),
        MailKind.REMINDER_2: (
            "Trotz unserer Zahlungserinnerung ist die Rechnung {nummer} noch offen. Bitte"
            " überweisen Sie {waehrung} {betrag} bis {faellig}. Die Mahnung finden Sie im Anhang."
        ),
        MailKind.REMINDER_3: (
            "Die Rechnung {nummer} ist trotz Mahnung noch offen. Bitte überweisen Sie"
            " {waehrung} {betrag} bis spätestens {faellig}. Die Mahnung finden Sie im Anhang."
        ),
    },
    Language.EN: {
        MailKind.INVOICE: (
            "Please find attached our invoice {nummer} for {waehrung} {betrag},"
            " payable by {faellig}."
        ),
        MailKind.QUOTE: (
            "Please find attached our quote {nummer} for {waehrung} {betrag}. It is valid"
            " until {faellig}. We look forward to your order."
        ),
        MailKind.CANCELLATION: "Please find attached the credit note {nummer}.",
        MailKind.REMINDER_1: (
            "Our invoice {nummer} is still open; perhaps it has escaped your attention."
            " Please pay {waehrung} {betrag} by {faellig}. The reminder is attached. If you have"
            " already paid, please disregard this message."
        ),
        MailKind.REMINDER_2: (
            "Despite our reminder, invoice {nummer} is still open. Please pay {waehrung} {betrag}"
            " by {faellig}. The reminder is attached."
        ),
        MailKind.REMINDER_3: (
            "Invoice {nummer} is still open despite our reminders. Please pay {waehrung} {betrag}"
            " by {faellig} at the latest. The final reminder is attached."
        ),
    },
}


def default_template(kind: MailKind, language: Language, country: Country) -> MailTemplate:
    """Return the built-in wording for the company's country."""
    terms = profile_of(country).terms[language]
    salutation, closing = terms.salutation, terms.closing
    body = f"{salutation}\n\n{_TEXTS[language][kind]}\n\n{closing}\n{{{Placeholder.COMPANY.value}}}"
    return MailTemplate(kind, language, _SUBJECTS[language][kind], body)
