from datetime import datetime
from typing import Self

from fastapi import APIRouter, status
from pydantic import Field

from rhinvoice.api.dependencies import NOT_IN_DEMO, ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.backup.handlers import BackupOverview, BackupState
from rhinvoice.application.backup.ports import BackupReason, BackupRun, BackupTarget, RunStatus

router = APIRouter(prefix="/api", tags=["backup"], responses=ERROR_RESPONSES)


class BackupRunResponse(ApiModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    reason: BackupReason
    status: RunStatus
    snapshot_id: str | None
    data_added: int | None
    """Bytes added to the repository (after deduplication)."""
    message: str | None

    @classmethod
    def of(cls, run: BackupRun) -> Self:
        return cls(
            id=run.id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            reason=run.reason,
            status=run.status,
            snapshot_id=run.snapshot_id,
            data_added=run.data_added,
            message=run.message,
        )


class BackupResponse(ApiModel):
    state: BackupState
    """not_set_up: no backup container or repository; stale: no success in 24 hours."""
    last_success: BackupRunResponse | None
    requested_at: datetime | None
    """A backup was requested and has not started yet."""
    runs: list[BackupRunResponse]

    @classmethod
    def of(cls, overview: BackupOverview) -> Self:
        return cls(
            state=overview.state,
            last_success=None
            if overview.last_success is None
            else BackupRunResponse.of(overview.last_success),
            requested_at=overview.requested_at,
            runs=[BackupRunResponse.of(run) for run in overview.runs],
        )


@router.get("/backup")
def get_backup(_user: CurrentUser, container: ContainerDep) -> BackupResponse:
    return BackupResponse.of(container.backup.overview())


@router.post("/backup", status_code=status.HTTP_202_ACCEPTED, dependencies=[NOT_IN_DEMO])
def request_backup(_user: CurrentUser, container: ContainerDep) -> BackupResponse:
    """Ask the backup container for a backup; it starts within about 30 seconds.

    409 backup_not_set_up when no backup container with a repository runs.
    """
    return BackupResponse.of(container.backup.request())


class FolderSuggestionResponse(ApiModel):
    name: str
    """The cloud service, e.g. "OneDrive"."""
    path: str


class BackupSetupResponse(ApiModel):
    """Folder and recovery key of the installation without Docker (ADR 0023)."""

    folder: str | None
    """Where the backups go; null before they are set up."""
    suggestions: list[FolderSuggestionResponse]
    """Folders cloud services keep in sync on this computer."""
    key_confirmed: bool

    @classmethod
    def of(cls, target: BackupTarget) -> Self:
        return cls(
            folder=target.folder,
            suggestions=[
                FolderSuggestionResponse(name=found.name, path=found.path)
                for found in target.suggestions
            ],
            key_confirmed=target.key_confirmed,
        )


class BackupSetupRequest(ApiModel):
    folder: str = Field(min_length=1, max_length=1000)


class RecoveryKeyResponse(ApiModel):
    key: str
    """Encrypts the backups; without it they cannot be restored."""


@router.get("/backup/setup")
def get_backup_setup(_user: CurrentUser, container: ContainerDep) -> BackupSetupResponse:
    """409 backup_by_container: in the Docker setup the backup container is set up instead."""
    return BackupSetupResponse.of(container.backup.target())


@router.put("/backup/setup", dependencies=[NOT_IN_DEMO])
def set_up_backups(
    body: BackupSetupRequest, _user: CurrentUser, container: ContainerDep
) -> RecoveryKeyResponse:
    """Back up into this folder; the first backup starts within about 30 seconds.

    The key stays the same when the folder changes. 422 backup_folder_unusable.
    """
    return RecoveryKeyResponse(key=container.backup.set_up(body.folder))


@router.get("/backup/key", dependencies=[NOT_IN_DEMO])
def get_recovery_key(_user: CurrentUser, container: ContainerDep) -> RecoveryKeyResponse:
    """409 backup_not_set_up before a folder is set up."""
    return RecoveryKeyResponse(key=container.backup.recovery_key())


@router.post("/backup/key/confirmed", dependencies=[NOT_IN_DEMO])
def confirm_recovery_key(_user: CurrentUser, container: ContainerDep) -> BackupSetupResponse:
    """Note that the key is kept elsewhere; the settings page stops asking for it."""
    return BackupSetupResponse.of(container.backup.confirm_key())
