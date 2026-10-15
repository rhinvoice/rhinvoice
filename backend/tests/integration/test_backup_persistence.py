"""Backup requests and runs: what the app writes and what the backup container records."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, insert, text
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.backup.handlers import BackupHandlers, BackupState
from rhinvoice.application.backup.ports import BackupFailed, BackupReason, RunStatus, Snapshot
from rhinvoice.application.backup.worker import BackupWorker
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.infrastructure.db.tables import backup_runs
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from tests.unit.domain import factories

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


class Archive:
    def __init__(self) -> None:
        self.error: str | None = None

    def back_up(self) -> Snapshot:
        if self.error is not None:
            raise BackupFailed(self.error)
        return Snapshot(snapshot_id="9b1c2d3e", data_added=52_000)

    def maintain(self, *, verify: bool) -> None:
        del verify


def test_the_programs_own_backups_are_recorded_like_the_containers(engine: Engine) -> None:
    """The settings page and the dashboard read them the same way (ADR 0023)."""
    with SqlUnitOfWork(engine) as uow:
        uow.company.save(factories.company())
        uow.commit()
    clock = FixedClock(NOW)
    archive = Archive()
    worker = BackupWorker(
        uow=lambda: SqlUnitOfWork(engine), clock=clock, archive=archive, zone=ZoneInfo("UTC")
    )
    backups = handlers(engine)

    def ask(at: datetime) -> None:
        # As the setup of the backup folder does (the settings page needs a first run).
        with SqlUnitOfWork(engine) as uow:
            uow.backups.request(BackupReason.MANUAL, at)
            uow.commit()

    ask(NOW)
    # A failed attempt keeps the request; the next one takes it.
    archive.error = "the folder cannot be reached"
    assert worker.tick() is BackupReason.MANUAL
    assert backups.overview().requested_at == NOW
    archive.error = None
    clock.set(NOW + timedelta(minutes=1))
    ask(NOW + timedelta(minutes=1))
    assert worker.tick() is BackupReason.MANUAL
    overview = backups.overview()
    assert overview.requested_at is None
    assert [(run.status, run.message) for run in overview.runs] == [
        (RunStatus.SUCCEEDED, None),
        (RunStatus.FAILED, "the folder cannot be reached"),
    ]
    assert overview.last_success is not None
    assert (overview.last_success.snapshot_id, overview.last_success.data_added) == (
        "9b1c2d3e",
        52_000,
    )
    # A run left running is marked failed at the next start; old handled requests go.
    with SqlUnitOfWork(engine) as uow:
        uow.backups.start_run(BackupReason.DOCUMENT, NOW + timedelta(minutes=2))
        uow.commit()
    worker.recover()
    assert backups.overview().runs[0].status is RunStatus.FAILED
    with SqlUnitOfWork(engine) as uow:
        assert uow.backups.runs_since(NOW + timedelta(minutes=1))[0].reason is BackupReason.MANUAL
        uow.backups.take_requests(backups.overview().runs[1].id, NOW + timedelta(days=31))
        uow.commit()
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM backup_requests")).scalar_one() == 0
