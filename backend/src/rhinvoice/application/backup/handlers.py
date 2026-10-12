"""State of the backups for the dashboard and the settings, and backups on request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.application.backup.ports import BackupReason, RunStatus
from rhinvoice.application.errors import ConflictError

if TYPE_CHECKING:
    from datetime import datetime

    from rhinvoice.application.backup.ports import BackupRun
    from rhinvoice.application.uow import UnitOfWorkFactory
    from rhinvoice.domain.shared.clock import Clock

RECENT_RUNS = 10
STALE_AFTER = timedelta(hours=24)
"""The dashboard warns when the last successful backup is older (CLAUDE.md §10)."""


class BackupState(StrEnum):
    NOT_SET_UP = "not_set_up"
    CURRENT = "current"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class BackupOverview:
    state: BackupState
    last_success: BackupRun | None
    requested_at: datetime | None
    """A backup was requested and has not started yet."""
    runs: list[BackupRun]


@dataclass(frozen=True, slots=True)
class BackupHandlers:
    uow: UnitOfWorkFactory
    clock: Clock

    def overview(self) -> BackupOverview:
        with self.uow() as uow:
            runs = uow.backups.runs(RECENT_RUNS)
            last_success = uow.backups.last_success()
            requested_at = uow.backups.pending_since()
        return BackupOverview(
            state=self._state(runs, last_success),
            last_success=last_success,
            requested_at=requested_at,
            runs=runs,
        )

    def request(self) -> BackupOverview:
        """Ask for a backup now; the backup container starts it within its poll interval."""
        if self.overview().state is BackupState.NOT_SET_UP:
            raise ConflictError(
                "backups are not set up (backup container, RESTIC_REPOSITORY)",
                code="backup_not_set_up",
            )
        with self.uow() as uow:
            uow.backups.request(BackupReason.MANUAL, self.clock.now())
            uow.commit()
        return self.overview()

    def _state(self, runs: list[BackupRun], last_success: BackupRun | None) -> BackupState:
        if not runs or runs[0].status is RunStatus.NOT_CONFIGURED:
            return BackupState.NOT_SET_UP
        if last_success is None or last_success.finished_at is None:
            return BackupState.STALE
        if self.clock.now() - last_success.finished_at > STALE_AFTER:
            return BackupState.STALE
        return BackupState.CURRENT
