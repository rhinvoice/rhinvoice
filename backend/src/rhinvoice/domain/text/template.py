"""Text templates (Textbausteine) for the texts of documents.

A template is a ready-made intro, closing or payment text per document type and
language. Templates marked as default are put into new documents, where they
can still be changed. Placeholders in curly braces are filled in when the
document is shown or printed, from the data of the document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_multiline, clean_text

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from rhinvoice.domain.shared.language import Language

MAX_NAME = 70
MAX_TEMPLATE_TEXT = 2000


class TextKind(StrEnum):
    INTRO = "intro"
    """Before the lines, e.g. "Thank you for your order."."""
    PAYMENT = "payment"
    """Payment terms after the totals, e.g. "Payable by {faellig}."."""
    CLOSING = "closing"
    """At the end, e.g. greetings."""


class Placeholder(StrEnum):
    """Placeholders users write into texts; the names are German like the product."""

    NUMBER = "nummer"
    DATE = "datum"
    DUE_DATE = "faellig"
    """Due date of invoices, validity of quotes."""
    CUSTOMER = "kunde"
    AMOUNT = "betrag"
    """Total of the document."""
    CURRENCY = "waehrung"
    COMPANY = "firma"
    """The company's name, e.g. under the greeting of a mail."""


_PLACEHOLDER = re.compile(r"\{([A-Za-z_]+)\}")
TEMPLATE_DOCUMENT_TYPES = frozenset({DocumentType.INVOICE, DocumentType.QUOTE})


def unknown_placeholders(text: str) -> list[str]:
    """Names in curly braces that are not placeholders, in order of appearance."""
    known = {placeholder.value for placeholder in Placeholder}
    found: list[str] = []
    for name in _PLACEHOLDER.findall(text):
        if name not in known and name not in found:
            found.append(name)
    return found


def fill_placeholders(text: str, values: Mapping[Placeholder, str]) -> str:
    """Replace the placeholders that have a value; all others stay as written."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        for placeholder, value in values.items():
            if placeholder.value == name:
                return value
        return match.group(0)

    return _PLACEHOLDER.sub(replace, text)


@dataclass(frozen=True, slots=True)
class TextTemplate:
    id: UUID
    kind: TextKind
    document_type: DocumentType
    language: Language
    name: str
    """Short label shown in the editor, e.g. "Payable without deduction"."""
    text: str
    is_default: bool = False
    """Put into new documents of the type and language."""
    position: int = 0
    """Order of the templates of a kind; defaults are joined in this order."""

    def __post_init__(self) -> None:
        if self.document_type not in TEMPLATE_DOCUMENT_TYPES:
            raise ValidationError("document_type", "templates are for invoices and quotes")
        object.__setattr__(
            self, "name", clean_text(self.name, "name", max_length=MAX_NAME, required=True)
        )
        text = clean_multiline(self.text, "text", max_length=MAX_TEMPLATE_TEXT)
        if not text:
            raise ValidationError("text", "text is required")
        unknown = unknown_placeholders(text)
        if unknown:
            allowed = ", ".join(f"{{{placeholder.value}}}" for placeholder in Placeholder)
            raise ValidationError(
                "text",
                f"unknown placeholder {{{unknown[0]}}}; available are {allowed}",
                code="unknown_placeholder",
            )
        object.__setattr__(self, "text", text)
