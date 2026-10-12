"""Use cases for number sequences."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rhinvoice.application.errors import ConflictError
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.numbering.sequence import NumberSequence, SequenceKind

if TYPE_CHECKING:
    from datetime import date

    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.shared.clock import Clock


def allocate_number(uow: UnitOfWork, kind: SequenceKind, on: date) -> str:
    """Take the next number for the date ``on`` in the caller's transaction (row lock, gapless)."""
    number, advanced = uow.sequences.lock(kind).allocate(on)
    uow.sequences.save(advanced)
    return number


@dataclass(frozen=True, slots=True)
class ConfigureSequence:
    kind: SequenceKind
    pattern: str
    start_value: int
    yearly_reset: bool
    next_value: int


@dataclass(frozen=True, slots=True)
class SequenceView:
    sequence: NumberSequence
    next_number: str
    next_counter: int
    """Effective counter of the next number (after a possible yearly reset)."""

    @classmethod
    def of(cls, sequence: NumberSequence, on: date) -> SequenceView:
        return cls(
            sequence=sequence,
            next_number=sequence.preview(on),
            next_counter=sequence.next_counter(on),
        )


@dataclass(frozen=True, slots=True)
class NumberingHandlers:
    uow: UnitOfWorkFactory
    clock: Clock

    def list(self) -> list[SequenceView]:
        """All kinds, with defaults for kinds that were never configured."""
        with self.uow() as uow:
            stored = {sequence.kind: sequence for sequence in uow.sequences.list()}
        today = self.clock.today()
        result: list[SequenceView] = []
        for kind in SequenceKind:
            sequence = stored.get(kind) or NumberSequence.default(kind)
            result.append(SequenceView.of(sequence, today))
        return result

    def preview(self, command: ConfigureSequence) -> str:
        """Next number for a configuration that is not saved yet."""
        return self._configured(command).preview(self.clock.today())

    def configure(self, command: ConfigureSequence) -> SequenceView:
        sequence = self._configured(command)
        next_number = sequence.preview(self.clock.today())
        with self.uow() as uow:
            # Lock the row so that no number is allocated while the format changes.
            uow.sequences.lock(command.kind)
            if number_in_use(uow, command.kind, next_number):
                message = f"the number {next_number} is already in use"
                raise ConflictError(message, details={"next_value": message})
            uow.sequences.save(sequence)
            uow.commit()
        return SequenceView.of(sequence, self.clock.today())

    def _configured(self, command: ConfigureSequence) -> NumberSequence:
        """Build the sequence; a reconfiguration replaces every setting."""
        return NumberSequence.default(command.kind).reconfigure(
            pattern=command.pattern.strip(),
            start_value=command.start_value,
            yearly_reset=command.yearly_reset,
            next_value=command.next_value,
            on=self.clock.today(),
        )


def number_in_use(uow: UnitOfWork, kind: SequenceKind, number: str) -> bool:
    """Whether a number of this kind already exists (protects against resetting a counter)."""
    if kind is SequenceKind.CUSTOMER:
        return uow.customers.number_exists(number)
    if kind is SequenceKind.ARTICLE:
        return uow.articles.number_exists(number)
    return uow.documents.number_exists(DocumentType(kind.value), number)
