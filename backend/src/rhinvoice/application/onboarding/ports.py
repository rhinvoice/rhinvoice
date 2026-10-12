"""What the onboarding checklist remembers beyond the data itself."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class OnboardingMarks:
    numbering_checked: bool
    """The number sequences were looked at (nothing in the data shows it)."""
    dismissed: bool
    """The checklist was hidden."""


class OnboardingRepository(Protocol):
    def marks(self) -> OnboardingMarks: ...
    def check_numbering(self, at: datetime) -> None: ...
    def dismiss(self, at: datetime) -> None: ...
    def show(self) -> None: ...
