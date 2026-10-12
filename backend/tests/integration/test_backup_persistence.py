"""Backup requests and runs: what the app writes and what the backup container records."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, insert, text
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.backup.handlers import BackupHandlers, BackupState
from rhinvoice.application.backup.ports import BackupReason, RunStatus
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.infrastructure.db.tables import backup_runs
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork

NOW = datetime(2026, 3, 9, 9, 0, tzinfo=UTC)


def handlers(engine: Engine) -> BackupHandlers:
    return BackupHandlers(uow=lambda: SqlUnitOfWork(engine), clock=FixedClock(NOW))


def test_requests_and_runs(engine: Engine) -> None:
    backups = handlers(engine)
    assert backups.overview().state is BackupState.NOT_SET_UP
    assert backups.overview().requested_at is None
    with engine.begin() as connection:
        # What the backup container records.
        connection.execute(
            insert(backup_runs).values(
                started_at=NOW - timedelta(hours=2),
                finished_at=NOW - timedelta(hours=2) + timedelta(seconds=30),
                reason="daily",
                status="succeeded",
                snapshot_id="4f3a9c1e",
                data_added=48_000,
            )
        )
    assert backups.request().requested_at == NOW
    with engine.begin() as connection:
        connection.execute(text("UPDATE backup_requests SET handled_at = now()"))
        connection.execute(
            insert(backup_runs).values(
                started_at=NOW - timedelta(hours=1),
                finished_at=NOW - timedelta(hours=1),
                reason="manual",
                status="failed",
                message="repository not reachable",
            )
        )
    overview = backups.overview()
    assert overview.state is BackupState.CURRENT
    assert overview.requested_at is None
    assert [(run.reason, run.status) for run in overview.runs] == [
        (BackupReason.MANUAL, RunStatus.FAILED),
        (BackupReason.DAILY, RunStatus.SUCCEEDED),
    ]
    assert overview.runs[0].message == "repository not reachable"
    assert overview.runs[0].snapshot_id is None
    assert overview.last_success is not None
    assert overview.last_success.snapshot_id == "4f3a9c1e"
    assert overview.last_success.data_added == 48_000
    assert overview.last_success.finished_at == NOW - timedelta(hours=2) + timedelta(seconds=30)


def test_unknown_reasons_and_states_are_refused(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(backup_runs).values(started_at=NOW, reason="weekly", status="succeeded")
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(backup_runs).values(started_at=NOW, reason="daily", status="done")
        )
