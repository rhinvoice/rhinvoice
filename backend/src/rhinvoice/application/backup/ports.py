"""Backups are made with restic, and the app requests and shows them.

The backup container makes them in the Docker setup, the program itself in the
installation without Docker (ADR 0023).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

REQUESTS_KEPT = timedelta(days=30)
"""Handled requests are removed after this time (as by the backup container)."""


class BackupReason(StrEnum):
    DAILY = "daily"
    DOCUMENT = "document"
    """A document was issued or cancelled."""
    MANUAL = "manual"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"
    """The backup container runs without a repository (RESTIC_REPOSITORY)."""


@dataclass(frozen=True, slots=True)
class BackupRun:
    id: int
    started_at: datetime
    finished_at: datetime | None
    reason: BackupReason
    status: RunStatus
    snapshot_id: str | None
    data_added: int | None
    """Bytes the run added to the repository (after deduplication)."""
    message: str | None


@dataclass(frozen=True, slots=True)
class PendingRequest:
    reason: BackupReason
    requested_at: datetime


@dataclass(frozen=True, slots=True)
class RunOutcome:
    status: RunStatus
    snapshot_id: str | None = None
    data_added: int | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class Snapshot:
    snapshot_id: str
    data_added: int | None
    """Bytes the backup added to the repository (after deduplication)."""


class BackupFailed(Exception):  # noqa: N818 - reads as the event it is
    """restic or pg_dump failed; the message is short enough for the settings page."""


@dataclass(frozen=True, slots=True)
class FolderSuggestion:
    """A folder a cloud service keeps in sync, found on this computer."""

    name: str
    """E.g. "OneDrive"."""
    path: str
    """The backup folder within it, as it would be used."""


@dataclass(frozen=True, slots=True)
class BackupTarget:
    folder: str | None
    """Where the backups go; None before they are set up."""
    suggestions: list[FolderSuggestion]
    key_confirmed: bool
    """The person confirmed that the recovery key is kept elsewhere."""


class BackupSetup(Protocol):
    """Folder and recovery key of the installation without Docker (ADR 0023)."""

    def target(self) -> BackupTarget:
        """Return the folder, the cloud folders found on this computer and the key's state."""
        ...

    def folder(self) -> str | None:
        """Return the folder the backups go to, without looking for cloud folders."""
        ...

    def set_up(self, folder: str) -> str:
        """Back up into ``folder`` (created when missing); return the recovery key.

        Raise BackupFailed when the folder cannot be used. The key stays the same for
        another folder: one key for every backup of this installation.
        """
        ...

    def recovery_key(self) -> str | None:
        """Return the key that encrypts the backups; None before they are set up."""
        ...

    def confirm_key(self) -> None:
        """Record that the key is kept elsewhere."""
        ...


class BackupArchive(Protocol):
    """The restic repository of the installation without Docker."""

    def back_up(self) -> Snapshot:
        """Save the database; raise BackupFailed with the reason."""
        ...

    def maintain(self, *, verify: bool) -> None:
        """Forget old backups by the retention rules; with ``verify`` also prune and check."""
        ...


class BackupRepository(Protocol):
    def request(self, reason: BackupReason, at: datetime) -> None:
        """Ask the backup container for a backup; it waits briefly for further requests."""
        ...

    def pending_since(self) -> datetime | None:
        """When the oldest request not yet taken by a run was made."""
        ...

    def runs(self, limit: int) -> list[BackupRun]:
        """Return the latest runs, newest first."""
        ...

    def last_success(self) -> BackupRun | None: ...

    # Used by the program's own backups (ADR 0023); the container writes these in SQL.

    def pending(self) -> list[PendingRequest]:
        """Return the requests no successful run has taken yet."""
        ...

    def runs_since(self, at: datetime) -> list[BackupRun]: ...

    def start_run(self, reason: BackupReason, at: datetime) -> int:
        """Record a run as running; return its id."""
        ...

    def finish_run(self, run_id: int, outcome: RunOutcome, at: datetime) -> None: ...

    def take_requests(self, run_id: int, at: datetime) -> None:
        """Mark the requests made before the run as handled; remove old handled ones."""
        ...

    def recover_runs(self, at: datetime, message: str) -> None:
        """Mark runs left running (the program ended meanwhile) as failed."""
        ...
