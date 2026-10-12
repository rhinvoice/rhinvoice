"""Number sequences for documents and master data.

A pattern such as ``R{YYYY}{NNNN}`` is expanded with the date and a counter.
Document numbers are only assigned when a document is issued, inside the
issuing transaction with a row lock (``SELECT ... FOR UPDATE``), so that
numbers are gapless and unique.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError

if TYPE_CHECKING:
    from datetime import date

MAX_PATTERN_LENGTH = 40
MAX_COUNTER = 10**12
_PLACEHOLDER = re.compile(r"\{([A-Z]+)\}")
_ALLOWED_LITERAL = re.compile(r"^[A-Za-z0-9\-_/.]*$")


class SequenceKind(StrEnum):
    INVOICE = "invoice"
    QUOTE = "quote"
    CANCELLATION = "cancellation"
    CUSTOMER = "customer"
    ARTICLE = "article"


MAX_NUMBER_LENGTH: dict[SequenceKind, int] = {
    SequenceKind.INVOICE: 30,
    SequenceKind.QUOTE: 30,
    SequenceKind.CANCELLATION: 30,
    SequenceKind.CUSTOMER: 20,
    SequenceKind.ARTICLE: 30,
}
"""Length of the number columns; longer numbers cannot be stored."""

DEFAULT_PATTERNS: dict[SequenceKind, tuple[str, int, bool]] = {
    SequenceKind.INVOICE: ("R{YYYY}{NNNN}", 1, True),
    SequenceKind.QUOTE: ("A{YYYY}{NNNN}", 1, True),
    SequenceKind.CANCELLATION: ("S{YYYY}{NNNN}", 1, True),
    SequenceKind.CUSTOMER: ("{NNNN}", 1001, False),
    SequenceKind.ARTICLE: ("{N}", 1, False),
}


def validate_pattern(pattern: str, *, yearly_reset: bool) -> None:
    if not pattern or len(pattern) > MAX_PATTERN_LENGTH:
        raise ValidationError("pattern", f"pattern must have 1 to {MAX_PATTERN_LENGTH} characters")
    placeholders = _PLACEHOLDER.findall(pattern)
    counters = [name for name in placeholders if set(name) == {"N"}]
    unknown = [
        name for name in placeholders if name not in {"YYYY", "YY", "MM"} and set(name) != {"N"}
    ]
    if unknown:
        raise ValidationError("pattern", f"unknown placeholder {{{unknown[0]}}}")
    if len(counters) != 1:
        raise ValidationError("pattern", "pattern must contain exactly one counter such as {NNNN}")
    literals = _PLACEHOLDER.split(pattern)[::2]
    if not all(_ALLOWED_LITERAL.fullmatch(literal) for literal in literals):
        raise ValidationError(
            "pattern",
            "pattern may only contain letters, digits and - _ / . besides placeholders",
        )
    if yearly_reset and not {"YYYY", "YY"} & set(placeholders):
        raise ValidationError(
            "pattern",
            "a yearly reset needs {YYYY} or {YY} in the pattern, otherwise numbers repeat",
        )


def format_number(pattern: str, counter: int, on: date) -> str:
    def expand(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "YYYY":
            return f"{on.year:04d}"
        if name == "YY":
            return f"{on.year % 100:02d}"
        if name == "MM":
            return f"{on.month:02d}"
        return f"{counter:0{len(name)}d}"

    return _PLACEHOLDER.sub(expand, pattern)


@dataclass(frozen=True, slots=True)
class NumberSequence:
    kind: SequenceKind
    pattern: str
    start_value: int
    yearly_reset: bool
    next_value: int
    """Counter used for the next number (before a possible yearly reset)."""
    last_year: int | None = None
    """Year of the last assigned number; drives the yearly reset."""

    def __post_init__(self) -> None:
        validate_pattern(self.pattern, yearly_reset=self.yearly_reset)
        if not 1 <= self.start_value < MAX_COUNTER:
            raise ValidationError("start_value", "start value must be a positive number")
        if not 1 <= self.next_value < MAX_COUNTER:
            raise ValidationError("next_value", "next value must be a positive number")

    @classmethod
    def default(cls, kind: SequenceKind) -> NumberSequence:
        pattern, start, reset = DEFAULT_PATTERNS[kind]
        return cls(
            kind=kind, pattern=pattern, start_value=start, yearly_reset=reset, next_value=start
        )

    def next_counter(self, on: date) -> int:
        """Counter the next allocation on ``on`` uses (after a possible yearly reset)."""
        return self._counter_for(on)

    def _counter_for(self, on: date) -> int:
        if self.yearly_reset and self.last_year is not None and on.year != self.last_year:
            return self.start_value
        return self.next_value

    def preview(self, on: date) -> str:
        """Return the number the next allocation on ``on`` would produce."""
        number = format_number(self.pattern, self._counter_for(on), on)
        limit = MAX_NUMBER_LENGTH[self.kind]
        if len(number) > limit:
            raise ValidationError(
                "pattern", f"numbers of this sequence must have at most {limit} characters"
            )
        return number

    def allocate(self, on: date) -> tuple[str, NumberSequence]:
        counter = self._counter_for(on)
        if counter + 1 >= MAX_COUNTER:
            raise ValidationError(
                "next_value", "the number sequence is exhausted, please reconfigure it"
            )
        number = self.preview(on)
        return number, replace(self, next_value=counter + 1, last_year=on.year)

    def reconfigure(
        self,
        *,
        pattern: str,
        start_value: int,
        yearly_reset: bool,
        next_value: int,
        on: date,
    ) -> NumberSequence:
        """Change the format, e.g. to continue seamlessly after a previous program.

        ``next_value`` is the counter of the next number in the year of ``on``;
        a yearly reset still happens when the next number falls into a later year.
        """
        return replace(
            self,
            pattern=pattern,
            start_value=start_value,
            yearly_reset=yearly_reset,
            next_value=next_value,
            last_year=on.year,
        )
