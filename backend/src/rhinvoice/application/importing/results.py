"""What an import did with each row of the file."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping

FIRST_DATA_ROW = 2
"""Row numbers as in the spreadsheet: row 1 holds the column names."""
PLACEHOLDER_NUMBER = "0"
"""Validates a new record before its number is taken from the sequence."""


class DuplicateStrategy(StrEnum):
    SKIP = "skip"
    UPDATE = "update"
    CREATE = "create"
    """Create a second record; a number that is taken gets the next free one."""


class RowStatus(StrEnum):
    NEW = "new"
    UPDATED = "updated"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RowProblem:
    field: str
    code: str
    """required, invalid, or a specific rule such as invalid_amount or unknown_unit."""
    message: str
    value: str = ""
    """The cell's text, if the file has one for the field."""


@dataclass(frozen=True, slots=True)
class RowOutcome:
    row: int
    """Row number in the file (the column names are row 1)."""
    status: RowStatus
    number: str
    """Number of the record (new ones: the number they get); empty for errors without one."""
    name: str
    detail: str
    """Postal code and city of a customer, the price of an article, the total of an invoice."""
    problem: RowProblem | None = None
    file: str | None = None
    """Invoices: the PDF that became the invoice, None without one."""
    attachments: int = 0
    """Invoices: further files of the same number (reminders, copies)."""
    new_customer: bool = False
    """Invoices: the customer was not known and has been created (archived)."""


# Domain fields that the import fills from another column.
_SOURCE_COLUMNS = {
    "postal_code": "postal_city",
    "city": "postal_city",
    "house_number": "street",
}


def error_outcome(row: int, error: ValidationError, cells: Mapping[str, str]) -> RowOutcome:
    name = (
        cells.get("company_name")
        or cells.get("last_name")
        or cells.get("name")
        or cells.get("customer_name", "")
    )
    value = cells.get(error.field) or cells.get(_SOURCE_COLUMNS.get(error.field, ""), "")
    code = error.code
    if code == ValidationError.code:
        # The domain's general code: say whether the value is missing or wrong.
        code = "invalid" if value else "required"
    return RowOutcome(
        row=row,
        status=RowStatus.ERROR,
        number=cells.get("number", ""),
        name=name,
        detail="",
        problem=RowProblem(field=error.field, code=code, message=error.message, value=value),
    )
