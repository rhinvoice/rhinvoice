"""What the onboarding checklist remembers (one row, created on first use)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from rhinvoice.application.onboarding.ports import OnboardingMarks
from rhinvoice.infrastructure.db.tables import onboarding

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy import Column, Connection


class SqlOnboardingRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def marks(self) -> OnboardingMarks:
        row = self._connection.execute(select(onboarding)).mappings().first()
        if row is None:
            return OnboardingMarks(numbering_checked=False, dismissed=False)
        return OnboardingMarks(
            numbering_checked=row["numbering_checked_at"] is not None,
            dismissed=row["dismissed_at"] is not None,
        )

    def check_numbering(self, at: datetime) -> None:
        self._mark(onboarding.c.numbering_checked_at, at)

    def dismiss(self, at: datetime) -> None:
        self._mark(onboarding.c.dismissed_at, at)

    def show(self) -> None:
        self._connection.execute(update(onboarding).values(dismissed_at=None))

    def _mark(self, column: Column[datetime], at: datetime) -> None:
        """Set the time once; later calls keep the first one."""
        statement = insert(onboarding).values({column.name: at})
        self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=[onboarding.c.singleton],
                set_={column.name: func.coalesce(column, statement.excluded[column.name])},
            )
        )
