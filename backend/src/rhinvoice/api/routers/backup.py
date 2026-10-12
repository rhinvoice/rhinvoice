from datetime import datetime
from typing import Self

from fastapi import APIRouter, status

from rhinvoice.api.dependencies import NOT_IN_DEMO, ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.backup.handlers import BackupOverview, BackupState
from rhinvoice.application.backup.ports import BackupReason, BackupRun, RunStatus

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
