from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from rhinvoice.domain.numbering.sequence import NumberSequence, SequenceKind


class NumberSequenceRepository(Protocol):
    def lock(self, kind: SequenceKind) -> NumberSequence:
        """Load the sequence and lock it until the transaction ends.

        A missing sequence is created with its defaults first, so that even the
        very first allocation is serialised (no duplicate first numbers).
        """
        ...

    def save(self, sequence: NumberSequence) -> None: ...

    def list(self) -> list[NumberSequence]: ...
