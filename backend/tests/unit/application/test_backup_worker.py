"""Backups made by the program itself (ADR 0023), by the rules of the backup container."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from rhinvoice.application.backup.ports import (
    BackupFailed,
    BackupReason,
    BackupRun,
    RunStatus,
    Snapshot,
)
from rhinvoice.application.backup.worker import MAX_WAIT, QUIET, BackupWorker
from rhinvoice.domain.shared.clock import FixedClock
from tests.unit.application.fakes import BackupRequest, InMemoryUnitOfWork, Store
from tests.unit.domain import factories

ZURICH = ZoneInfo("Europe/Zurich")
# Monday, 9 March 2026, 10:00 in Zurich.
MONDAY = datetime(2026, 3, 9, 10, 0, tzinfo=ZURICH)


class Archive:
    """Stands in for restic: counts backups, and fails when told to."""

    def __init__(self) -> None:
        self.backups = 0
        self.maintained: list[bool] = []
        self.backup_error: str | None = None
        self.maintain_error: str | None = None
        self.crash: Exception | None = None
        """An error the archive should never raise, but might (a bug, a vanished program)."""
        self.maintain_crash: Exception | None = None

    def back_up(self) -> Snapshot:
        if self.crash is not None:
            raise self.crash
        if self.backup_error is not None:
            raise BackupFailed(self.backup_error)
        self.backups += 1
        return Snapshot(snapshot_id=f"snap{self.backups}", data_added=1000 * self.backups)

    def maintain(self, *, verify: bool) -> None:
        if self.maintain_crash is not None:
            raise self.maintain_crash
        if self.maintain_error is not None:
            raise BackupFailed(self.maintain_error)
        self.maintained.append(verify)


class Setup:
    def __init__(self, at: datetime = MONDAY, *, company: bool = True) -> None:
        self.store = Store()
        if company:
            self.store.company = factories.company()
        self.clock = FixedClock(at, ZURICH)
        self.earlier = 0
        """Runs before the test's own (the daily backup the fixture made)."""
        self.archive = Archive()
        self.worker = BackupWorker(
            uow=lambda: InMemoryUnitOfWork(self.store),
            clock=self.clock,
            archive=self.archive,
            zone=ZURICH,
        )

    def at(self, moment: datetime) -> None:
        self.clock.set(moment)

    def later(self, delta: timedelta) -> None:
        self.clock.set(self.clock.now() + delta)

    def request(self, reason: BackupReason, ago: timedelta = timedelta(0)) -> None:
        self.store.backup_requests.append(BackupRequest(reason, self.clock.now() - ago))

    def runs(self) -> list[BackupRun]:
        return self.store.backup_runs[self.earlier :]

    def statuses(self) -> list[tuple[BackupReason, RunStatus]]:
        return [(run.reason, run.status) for run in self.runs()]


@pytest.fixture
def setup() -> Setup:
    """Set up a company on Monday 10:00, with today's daily backup made."""
    made = Setup()
    made.at(MONDAY.replace(hour=2))
    made.worker.tick()
    made.at(MONDAY)
    made.earlier = len(made.store.backup_runs)
    return made


def test_without_a_company_nothing_is_backed_up() -> None:
    """An empty database must never become the latest backup."""
    fresh = Setup(company=False)
    fresh.request(BackupReason.MANUAL)
    assert fresh.worker.tick() is None
    assert fresh.store.backup_runs == []
    assert fresh.archive.backups == 0


def test_the_daily_backup_runs_once_from_two_in_the_morning() -> None:
    early = Setup(MONDAY.replace(hour=1, minute=59))
    assert early.worker.tick() is None
    early.later(timedelta(minutes=1))
    assert early.worker.tick() is BackupReason.DAILY
    assert early.statuses() == [(BackupReason.DAILY, RunStatus.SUCCEEDED)]
    [run] = early.store.backup_runs
    assert (run.snapshot_id, run.data_added) == ("snap1", 1000)
    assert run.finished_at == early.clock.now()
    # Forget the old ones every day; verify a sample on Sundays only.
    assert early.archive.maintained == [False]
    early.later(timedelta(hours=10))
    assert early.worker.tick() is None


def test_on_sundays_a_sample_of_the_backups_is_verified() -> None:
    sunday = Setup(datetime(2026, 3, 8, 2, 0, tzinfo=ZURICH))
    sunday.worker.tick()
    assert sunday.archive.maintained == [True]


def test_a_failed_daily_backup_is_tried_again_after_half_an_hour() -> None:
    nightly = Setup(MONDAY.replace(hour=2))
    nightly.archive.backup_error = "the folder cannot be reached"
    assert nightly.worker.tick() is BackupReason.DAILY
    nightly.archive.backup_error = None
    nightly.later(timedelta(minutes=29))
    assert nightly.worker.tick() is None
    nightly.later(timedelta(minutes=2))
    assert nightly.worker.tick() is BackupReason.DAILY
    assert nightly.statuses() == [
        (BackupReason.DAILY, RunStatus.FAILED),
        (BackupReason.DAILY, RunStatus.SUCCEEDED),
    ]
    assert nightly.store.backup_runs[0].message == "the folder cannot be reached"


def test_a_backup_asked_for_by_hand_runs_at_once(setup: Setup) -> None:
    setup.request(BackupReason.MANUAL)
    assert setup.worker.tick() is BackupReason.MANUAL
    assert setup.store.backup_requests[0].handled
    assert setup.worker.tick() is None


def test_issued_documents_wait_for_a_quiet_moment(setup: Setup) -> None:
    """Several documents in a row give one backup."""
    setup.request(BackupReason.DOCUMENT)
    setup.later(QUIET - timedelta(seconds=1))
    assert setup.worker.tick() is None
    setup.later(timedelta(seconds=1))
    assert setup.worker.tick() is BackupReason.DOCUMENT
    assert setup.statuses() == [(BackupReason.DOCUMENT, RunStatus.SUCCEEDED)]


def test_a_steady_stream_of_documents_waits_at_most_a_quarter_of_an_hour(setup: Setup) -> None:
    setup.request(BackupReason.DOCUMENT, ago=MAX_WAIT - timedelta(seconds=1))
    setup.request(BackupReason.DOCUMENT)
    assert setup.worker.tick() is None
    setup.later(timedelta(seconds=1))
    assert setup.worker.tick() is BackupReason.DOCUMENT


def test_after_a_failure_documents_wait_but_a_request_by_hand_does_not(setup: Setup) -> None:
    setup.archive.backup_error = "disk full"
    setup.request(BackupReason.MANUAL)
    assert setup.worker.tick() is BackupReason.MANUAL
    setup.archive.backup_error = None
    # The failed request stays open; documents wait 15 minutes after a failure.
    assert not setup.store.backup_requests[0].handled
    setup.request(BackupReason.DOCUMENT, ago=QUIET)
    assert setup.worker.tick() is None
    setup.later(timedelta(minutes=1))
    setup.request(BackupReason.MANUAL)
    assert setup.worker.tick() is BackupReason.MANUAL
    assert all(request.handled for request in setup.store.backup_requests)


def test_documents_are_backed_up_again_once_the_failure_is_a_quarter_of_an_hour_old(
    setup: Setup,
) -> None:
    setup.archive.backup_error = "disk full"
    setup.request(BackupReason.DOCUMENT, ago=QUIET)
    assert setup.worker.tick() is BackupReason.DOCUMENT
    setup.archive.backup_error = None
    setup.later(timedelta(minutes=14, seconds=59))
    assert setup.worker.tick() is None
    setup.later(timedelta(seconds=1))
    assert setup.worker.tick() is BackupReason.DOCUMENT
    assert setup.statuses() == [
        (BackupReason.DOCUMENT, RunStatus.FAILED),
        (BackupReason.DOCUMENT, RunStatus.SUCCEEDED),
    ]


def test_a_failed_maintenance_keeps_the_backup(setup: Setup) -> None:
    nightly = Setup(MONDAY.replace(hour=2))
    nightly.archive.maintain_error = "the repository is locked"
    nightly.worker.tick()
    [run] = nightly.store.backup_runs
    assert run.status is RunStatus.SUCCEEDED
    assert (
        run.message == "backed up, but the repository maintenance failed: the repository is locked"
    )
    del setup


def test_runs_left_running_by_a_stopped_program_are_marked_failed(setup: Setup) -> None:
    setup.request(BackupReason.MANUAL)
    setup.worker.tick()
    with InMemoryUnitOfWork(setup.store) as uow:
        uow.backups.start_run(BackupReason.DOCUMENT, setup.clock.now())
        uow.commit()
    setup.worker.recover()
    assert setup.statuses() == [
        (BackupReason.MANUAL, RunStatus.SUCCEEDED),
        (BackupReason.DOCUMENT, RunStatus.FAILED),
    ]
    assert setup.runs()[1].message == "interrupted: the program ended during the backup"


def test_old_handled_requests_are_removed(setup: Setup) -> None:
    setup.store.backup_requests.append(
        BackupRequest(
            BackupReason.DOCUMENT,
            datetime(2026, 1, 1, tzinfo=UTC),
            handled=True,
            handled_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    setup.request(BackupReason.MANUAL)
    setup.worker.tick()
    assert [request.reason for request in setup.store.backup_requests] == [BackupReason.MANUAL]


def test_an_unexpected_error_fails_the_run_instead_of_leaving_it_running(
    setup: Setup, caplog: pytest.LogCaptureFixture
) -> None:
    """A run left running would block the daily backup and start anew every half minute."""
    setup.archive.crash = UnicodeDecodeError("utf-8", b"\xe8", 0, 1, "invalid start byte")
    setup.request(BackupReason.MANUAL)
    assert setup.worker.tick() is BackupReason.MANUAL
    [run] = setup.runs()
    assert run.status is RunStatus.FAILED
    assert run.message == (
        "unexpected error: UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe8 "
        "in position 0: invalid start byte"
    )
    assert "backup failed unexpectedly" in caplog.text


def test_an_unexpected_error_in_the_maintenance_keeps_the_backup() -> None:
    nightly = Setup(MONDAY.replace(hour=2))
    nightly.archive.maintain_crash = OSError("restic vanished")
    nightly.worker.tick()
    [run] = nightly.store.backup_runs
    assert run.status is RunStatus.SUCCEEDED
    assert run.message == (
        "backed up, but the repository maintenance failed: "
        "unexpected error: OSError: restic vanished"
    )
