"""Backup requests of the app and the runs of the backups (container or program, ADR 0023)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, insert, select, update

from rhinvoice.application.backup.ports import (
    REQUESTS_KEPT,
    BackupReason,
    BackupRun,
    PendingRequest,
    RunStatus,
)
from rhinvoice.infrastructure.db.tables import backup_requests, backup_runs

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy import Connection, RowMapping

    from rhinvoice.application.backup.ports import RunOutcome


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

    def pending(self) -> list[PendingRequest]:
        statement = (
            select(backup_requests.c.reason, backup_requests.c.requested_at)
            .where(backup_requests.c.handled_at.is_(None))
            .order_by(backup_requests.c.requested_at)
        )
        return [
            PendingRequest(BackupReason(row["reason"]), row["requested_at"])
            for row in self._connection.execute(statement).mappings()
        ]

    def runs_since(self, at: datetime) -> list[BackupRun]:
        statement = (
            select(backup_runs).where(backup_runs.c.started_at >= at).order_by(backup_runs.c.id)
        )
        return [_run_from_row(row) for row in self._connection.execute(statement).mappings()]

    def start_run(self, reason: BackupReason, at: datetime) -> int:
        statement = (
            insert(backup_runs)
            .values(started_at=at, reason=reason.value, status=RunStatus.RUNNING.value)
            .returning(backup_runs.c.id)
        )
        run_id: int = self._connection.execute(statement).scalar_one()
        return run_id

    def finish_run(self, run_id: int, outcome: RunOutcome, at: datetime) -> None:
        self._connection.execute(
            update(backup_runs)
            .where(backup_runs.c.id == run_id)
            .values(
                finished_at=at,
                status=outcome.status.value,
                snapshot_id=outcome.snapshot_id,
                data_added=outcome.data_added,
                message=outcome.message,
            )
        )

    def take_requests(self, run_id: int, at: datetime) -> None:
        started = (
            select(backup_runs.c.started_at).where(backup_runs.c.id == run_id).scalar_subquery()
        )
        self._connection.execute(
            update(backup_requests)
            .where(
                backup_requests.c.handled_at.is_(None), backup_requests.c.requested_at <= started
            )
            .values(handled_at=at)
        )
        self._connection.execute(
            delete(backup_requests).where(backup_requests.c.handled_at < at - REQUESTS_KEPT)
        )

    def recover_runs(self, at: datetime, message: str) -> None:
        self._connection.execute(
            update(backup_runs)
            .where(backup_runs.c.status == RunStatus.RUNNING.value)
            .values(status=RunStatus.FAILED.value, finished_at=at, message=message)
        )
