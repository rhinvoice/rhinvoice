"""Backup requests of the app and the runs the backup container records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, insert, select

from rhinvoice.application.backup.ports import BackupReason, BackupRun, RunStatus
from rhinvoice.infrastructure.db.tables import backup_requests, backup_runs

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy import Connection, RowMapping


def _run_from_row(row: RowMapping) -> BackupRun:
    return BackupRun(
        id=row["id"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        reason=BackupReason(row["reason"]),
        status=RunStatus(row["status"]),
        snapshot_id=row["snapshot_id"],
        data_added=row["data_added"],
        message=row["message"],
    )


class SqlBackupRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def request(self, reason: BackupReason, at: datetime) -> None:
        self._connection.execute(
            insert(backup_requests).values(requested_at=at, reason=reason.value)
        )

    def pending_since(self) -> datetime | None:
        statement = select(func.min(backup_requests.c.requested_at)).where(
            backup_requests.c.handled_at.is_(None)
        )
        oldest: datetime | None = self._connection.execute(statement).scalar_one()
        return oldest

    def runs(self, limit: int) -> list[BackupRun]:
        statement = select(backup_runs).order_by(backup_runs.c.id.desc()).limit(limit)
        return [_run_from_row(row) for row in self._connection.execute(statement).mappings()]

    def last_success(self) -> BackupRun | None:
        statement = (
            select(backup_runs)
            .where(backup_runs.c.status == RunStatus.SUCCEEDED.value)
            .order_by(backup_runs.c.id.desc())
            .limit(1)
        )
        row = self._connection.execute(statement).mappings().first()
        return None if row is None else _run_from_row(row)
