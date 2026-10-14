"""Backups made by the program itself (installation without Docker, ADR 0023).

The same rules as the backup container (backup/rhinvoice-backup.sh, docs/backup.md):
daily at two in the morning, a quiet moment after documents were issued or cancelled,
at once when asked for by hand; after a failure documents wait a quarter of an hour and
the daily backup half an hour. Nothing is backed up before a company is set up: an empty
database must never become the latest backup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING

from rhinvoice.application.backup.ports import (
    BackupFailed,
    BackupReason,
    RunOutcome,
    RunStatus,
)

if TYPE_CHECKING:
    from datetime import tzinfo

    from rhinvoice.application.backup.ports import BackupArchive, BackupRun, PendingRequest
    from rhinvoice.application.uow import UnitOfWorkFactory
    from rhinvoice.domain.shared.clock import Clock

logger = logging.getLogger(__name__)

DAILY_AT = time(2, 0)
QUIET = timedelta(seconds=120)
"""Several documents in a row give one backup: it starts after this quiet time ..."""
MAX_WAIT = timedelta(seconds=900)
"""... but at the latest this long after the first request."""
DAILY_RETRY = timedelta(minutes=30)
DOCUMENT_RETRY = timedelta(minutes=15)
INTERRUPTED = "interrupted: the program ended during the backup"
SUNDAY = 6


@dataclass(frozen=True, slots=True)
class BackupWorker:
    uow: UnitOfWorkFactory
    clock: Clock
    archive: BackupArchive
    zone: tzinfo
    """The time zone of the daily backup."""

    def recover(self) -> None:
        """Mark runs left running by an earlier start as failed (at the start)."""
        with self.uow() as uow:
            uow.backups.recover_runs(self.clock.now(), INTERRUPTED)
            uow.commit()

    def tick(self) -> BackupReason | None:
        """Make the backup that is due, if any (called every half minute); return its reason."""
        now = self.clock.now()
        with self.uow() as uow:
            if uow.company.get() is None:
                return None
            reason = self._requested(
                uow.backups.pending(), uow.backups.runs_since(now - MAX_WAIT), now
            )
            if reason is None and self._daily_due(uow.backups.runs_since(self._today_at(now)), now):
                reason = BackupReason.DAILY
        if reason is not None:
            self._back_up(reason)
        return reason

    def _today_at(self, now: datetime) -> datetime:
        local = now.astimezone(self.zone)
        return datetime.combine(local.date(), DAILY_AT, tzinfo=self.zone)

    def _daily_due(self, runs: list[BackupRun], now: datetime) -> bool:
        if now < self._today_at(now):
            return False
        return not any(
            run.reason is BackupReason.DAILY
            and (
                run.status in {RunStatus.SUCCEEDED, RunStatus.RUNNING}
                or run.started_at > now - DAILY_RETRY
            )
            for run in runs
        )

    @staticmethod
    def _requested(
        pending: list[PendingRequest], recent: list[BackupRun], now: datetime
    ) -> BackupReason | None:
        if not pending:
            return None
        failures = [
            run.started_at
            for run in recent
            if run.status is RunStatus.FAILED and run.started_at > now - DOCUMENT_RETRY
        ]
        failed_at = max(failures, default=None)
        if any(
            request.reason is BackupReason.MANUAL
            and (failed_at is None or request.requested_at > failed_at)
            for request in pending
        ):
            return BackupReason.MANUAL
        if failed_at is not None:
            return None
        newest = max(request.requested_at for request in pending)
        oldest = min(request.requested_at for request in pending)
        if newest <= now - QUIET or oldest <= now - MAX_WAIT:
            return BackupReason.DOCUMENT
        return None

    def _back_up(self, reason: BackupReason) -> None:
        with self.uow() as uow:
            run_id = uow.backups.start_run(reason, self.clock.now())
            uow.commit()
        try:
            snapshot = self.archive.back_up()
        # Any error ends the run: one left running would block the daily backup and start
        # anew every half minute.
        except Exception as error:  # noqa: BLE001
            outcome = RunOutcome(RunStatus.FAILED, message=_message(error))
            self._finish(run_id, outcome, handled=False)
            return
        message = None
        if reason is BackupReason.DAILY:
            local = self.clock.now().astimezone(self.zone)
            try:
                self.archive.maintain(verify=local.weekday() == SUNDAY)
            except Exception as error:  # noqa: BLE001 - the backup itself is made
                message = f"backed up, but the repository maintenance failed: {_message(error)}"
        outcome = RunOutcome(
            RunStatus.SUCCEEDED, snapshot.snapshot_id, snapshot.data_added, message
        )
        self._finish(run_id, outcome, handled=True)

    def _finish(self, run_id: int, outcome: RunOutcome, *, handled: bool) -> None:
        with self.uow() as uow:
            now = self.clock.now()
            uow.backups.finish_run(run_id, outcome, now)
            if handled:
                uow.backups.take_requests(run_id, now)
            uow.commit()


def _message(error: Exception) -> str:
    """Name a failure for the settings page; an unexpected one is also logged."""
    if isinstance(error, BackupFailed):
        return str(error)
    logger.error("backup failed unexpectedly", exc_info=error)
    return f"unexpected error: {type(error).__name__}: {error}"
