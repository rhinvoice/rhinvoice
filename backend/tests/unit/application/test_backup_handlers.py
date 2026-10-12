from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

from rhinvoice.application.backup.handlers import (
    RECENT_RUNS,
    STALE_AFTER,
    BackupHandlers,
    BackupState,
)
from rhinvoice.application.backup.ports import BackupReason, BackupRun, RunStatus
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.errors import ConflictError
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import ValidationError
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import BackupRequest, InMemoryUnitOfWork, Store
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)


def run(
    run_id: int,
    status: RunStatus = RunStatus.SUCCEEDED,
    *,
    ago: timedelta = timedelta(hours=1),
    reason: BackupReason = BackupReason.DAILY,
) -> BackupRun:
    started = NOW - ago
    return BackupRun(
        id=run_id,
        started_at=started,
        finished_at=None if status is RunStatus.RUNNING else started + timedelta(seconds=20),
        reason=reason,
        status=status,
        snapshot_id="4f3a9c1e" if status is RunStatus.SUCCEEDED else None,
        data_added=48_000 if status is RunStatus.SUCCEEDED else None,
        message="repository not reachable" if status is RunStatus.FAILED else None,
    )


def handlers(store: Store, clock: FixedClock) -> BackupHandlers:
    return BackupHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


def test_without_runs_backups_are_not_set_up(store: Store, clock: FixedClock) -> None:
    overview = handlers(store, clock).overview()
    assert overview.state is BackupState.NOT_SET_UP
    assert overview.last_success is None
    assert overview.requested_at is None
    assert overview.runs == []
    # A backup container without a repository reports itself.
    store.backup_runs = [run(1), run(2, RunStatus.NOT_CONFIGURED)]
    assert handlers(store, clock).overview().state is BackupState.NOT_SET_UP


def test_backups_are_current_for_24_hours(store: Store, clock: FixedClock) -> None:
    store.backup_runs = [run(1, ago=timedelta(days=3)), run(2, ago=timedelta(hours=2))]
    overview = handlers(store, clock).overview()
    assert overview.state is BackupState.CURRENT
    assert overview.last_success == store.backup_runs[1]
    assert [item.id for item in overview.runs] == [2, 1]
    # Finished exactly 24 hours ago: still current; a second later: stale.
    finished = NOW - STALE_AFTER
    store.backup_runs = [replace(run(1), finished_at=finished)]
    assert handlers(store, clock).overview().state is BackupState.CURRENT
    store.backup_runs = [replace(run(1), finished_at=finished - timedelta(seconds=1))]
    assert handlers(store, clock).overview().state is BackupState.STALE


def test_failed_and_running_backups(store: Store, clock: FixedClock) -> None:
    store.backup_runs = [run(1, RunStatus.FAILED)]
    overview = handlers(store, clock).overview()
    assert overview.state is BackupState.STALE
    assert overview.last_success is None
    # A failure after a recent success keeps the backup current.
    store.backup_runs = [run(1, ago=timedelta(hours=3)), run(2, RunStatus.FAILED)]
    assert handlers(store, clock).overview().state is BackupState.CURRENT
    store.backup_runs = [run(1, ago=timedelta(hours=3)), run(2, RunStatus.RUNNING)]
    overview = handlers(store, clock).overview()
    assert overview.state is BackupState.CURRENT
    assert overview.runs[0].status is RunStatus.RUNNING


def test_only_the_latest_runs_are_listed(store: Store, clock: FixedClock) -> None:
    store.backup_runs = [run(index, ago=timedelta(hours=30 - index)) for index in range(15)]
    runs = handlers(store, clock).overview().runs
    assert len(runs) == RECENT_RUNS
    assert runs[0].id == 14


def test_backups_on_request(store: Store, clock: FixedClock) -> None:
    with raises_exactly(
        ConflictError, "backups are not set up (backup container, RESTIC_REPOSITORY)"
    ) as refused:
        handlers(store, clock).request()
    assert refused.value.code == "backup_not_set_up"
    assert store.backup_requests == []
    store.backup_runs = [run(1)]
    overview = handlers(store, clock).request()
    assert store.backup_requests == [BackupRequest(BackupReason.MANUAL, NOW)]
    assert overview.requested_at == NOW
    store.backup_requests = [
        BackupRequest(BackupReason.DOCUMENT, NOW - timedelta(minutes=9), handled=True),
        BackupRequest(BackupReason.DOCUMENT, NOW - timedelta(minutes=3)),
        BackupRequest(BackupReason.MANUAL, NOW - timedelta(minutes=1)),
    ]
    assert handlers(store, clock).overview().requested_at == NOW - timedelta(minutes=3)


def test_issuing_and_cancelling_request_a_backup(store: Store, clock: FixedClock) -> None:
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    documents = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    line = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="100")
    draft = documents.create(DocumentType.INVOICE, DraftInput(customer_id=CUSTOMER, lines=(line,)))
    assert store.backup_requests == []
    documents.issue(draft.document.id)
    assert store.backup_requests == [BackupRequest(BackupReason.DOCUMENT, NOW)]
    documents.cancel(draft.document.id)
    assert len(store.backup_requests) == 2
    # A refused issue requests nothing.
    empty = documents.create(DocumentType.INVOICE, DraftInput(customer_id=CUSTOMER, lines=()))
    with pytest.raises(ValidationError):
        documents.issue(empty.document.id)
    assert len(store.backup_requests) == 2
