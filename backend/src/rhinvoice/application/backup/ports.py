"""Backups are made by the backup container (restic); the app requests them and shows them."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime


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
