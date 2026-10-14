"""Setting up the backups of the installation without Docker (ADR 0023)."""

from collections.abc import Callable

import pytest

from rhinvoice.application.backup.handlers import BackupHandlers, BackupState
from rhinvoice.application.backup.ports import (
    BackupFailed,
    BackupReason,
    BackupTarget,
    FolderSuggestion,
)
from rhinvoice.application.errors import ConflictError
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import ValidationError
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import BackupRequest, InMemoryUnitOfWork, Store

ONEDRIVE = FolderSuggestion(name="OneDrive", path="/Users/anna/OneDrive/Rhinvoice-Sicherung")


class Setup:
    """Stands in for the program's folder and key handling."""

    def __init__(self) -> None:
        self.chosen: str | None = None
        self.key: str | None = None
        self.confirmed = False
        self.refuse: str | None = None

    def folder(self) -> str | None:
        return self.chosen

    def target(self) -> BackupTarget:
        return BackupTarget(
            folder=self.chosen, suggestions=[ONEDRIVE], key_confirmed=self.confirmed
        )

    def set_up(self, folder: str) -> str:
        if self.refuse is not None:
            raise BackupFailed(self.refuse)
        self.chosen = folder
        self.key = self.key or "K7QM-2XWP-9DTA-F4NR"
        return self.key

    def recovery_key(self) -> str | None:
        return self.key

    def confirm_key(self) -> None:
        self.confirmed = True


def handlers(store: Store, setup: Setup | None) -> BackupHandlers:
    return BackupHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=FixedClock(NOW), setup=setup)


@pytest.fixture
def store() -> Store:
    return Store()


def test_a_folder_is_set_up_and_backed_up_at_once(store: Store) -> None:
    setup = Setup()
    backups = handlers(store, setup)
    assert backups.target() == BackupTarget(
        folder=None, suggestions=[ONEDRIVE], key_confirmed=False
    )
    assert backups.set_up(ONEDRIVE.path) == "K7QM-2XWP-9DTA-F4NR"
    assert backups.target().folder == ONEDRIVE.path
    # The first backup is asked for right away: the settings page shows it soon.
    assert store.backup_requests == [BackupRequest(BackupReason.MANUAL, NOW)]
    assert backups.overview().requested_at == NOW
    assert backups.overview().state is BackupState.NOT_SET_UP


def test_the_key_is_shown_until_it_was_kept_and_on_request(store: Store) -> None:
    setup = Setup()
    backups = handlers(store, setup)
    backups.set_up(ONEDRIVE.path)
    assert backups.recovery_key() == "K7QM-2XWP-9DTA-F4NR"
    assert backups.confirm_key().key_confirmed
    # Another folder keeps the key: one key for every backup of this installation.
    assert backups.set_up("/Volumes/USB/Rhinvoice") == "K7QM-2XWP-9DTA-F4NR"
    assert backups.target().key_confirmed


def test_a_folder_that_cannot_be_used_is_refused_with_the_reason(store: Store) -> None:
    setup = Setup()
    setup.refuse = "the folder cannot be written"
    with raises_exactly(ValidationError, "the folder cannot be written") as refused:
        handlers(store, setup).set_up("/read-only")
    assert refused.value.field == "folder"
    assert refused.value.code == "backup_folder_unusable"
    assert store.backup_requests == []


def test_without_a_key_there_is_nothing_to_show(store: Store) -> None:
    with raises_exactly(ConflictError, "backups are not set up yet") as refused:
        handlers(store, Setup()).recovery_key()
    assert refused.value.code == "backup_not_set_up"


SETUP_CALLS: list[Callable[[BackupHandlers], object]] = [
    lambda backups: backups.target(),
    lambda backups: backups.set_up("/x"),
    lambda backups: backups.recovery_key(),
    lambda backups: backups.confirm_key(),
]


@pytest.mark.parametrize("call", SETUP_CALLS)
def test_in_the_docker_setup_the_backup_container_is_set_up_instead(
    store: Store, call: Callable[[BackupHandlers], object]
) -> None:
    with raises_exactly(
        ConflictError, "backups are set up in the backup container here (docs/backup.md)"
    ) as refused:
        call(handlers(store, None))
    assert refused.value.code == "backup_by_container"
