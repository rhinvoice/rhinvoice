from datetime import datetime
from typing import Self

from fastapi import APIRouter, status

from rhinvoice.api.dependencies import NOT_IN_DEMO, ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel, ErrorResponse
from rhinvoice.application.updates.handlers import UpdateAction, UpdateStatus
from rhinvoice.application.updates.ports import SetupProgress, SetupState

router = APIRouter(prefix="/api", tags=["updates"], responses=ERROR_RESPONSES)


class SetupResponse(ApiModel):
    state: SetupState
    """idle: not asked for; downloading; ready: downloaded and checked; failed."""
    received: int
    total: int
    """Bytes."""

    @classmethod
    def of(cls, progress: SetupProgress) -> Self:
        return cls(state=progress.state, received=progress.received, total=progress.total)


class UpdateResponse(ApiModel):
    current: str
    latest: str | None
    """The newest release; None before the first check or with the check switched off."""
    action: UpdateAction
    """none: up to date; command: a server installation (docker compose pull); install:
    the installation without Docker installs it; setup: it needs a new setup first."""
    notes_url: str | None
    setup_url: str | None
    checked_at: datetime | None
    failed: bool
    """The newest release did not start here and was taken back; it is not offered again."""
    can_check: bool
    """POST /api/updates/check may be used; False with the check switched off."""
    setup: SetupResponse | None
    """With action "setup": the program downloads and runs the setup itself (ADR 0031);
    None: only setup_url, to download by hand."""
    pinned: bool | None
    """With action "command": True when RHINVOICE_VERSION in .env has to change before the
    pull, False when the pull alone brings the release (latest); None: not known."""

    @classmethod
    def of(cls, update: UpdateStatus) -> Self:
        return cls(
            current=update.current,
            latest=update.latest,
            action=update.action,
            notes_url=update.notes_url,
            setup_url=update.setup_url,
            checked_at=update.checked_at,
            failed=update.failed,
            can_check=update.can_check,
            setup=None if update.setup is None else SetupResponse.of(update.setup),
            pinned=update.pinned,
        )


@router.get("/updates")
def get_updates(_user: CurrentUser, container: ContainerDep) -> UpdateResponse:
    """Whether a newer release exists (checked once a day, RHINVOICE_UPDATE_CHECK)."""
    return UpdateResponse.of(container.updates.status())


CHECK_RESPONSES: dict[int | str, dict[str, object]] = {
    503: {"model": ErrorResponse, "description": "Switched off, or no answer about releases"},
}


@router.post("/updates/check", responses=CHECK_RESPONSES)
def check_updates(_user: CurrentUser, container: ContainerDep) -> UpdateResponse:
    """Ask for the newest release now instead of waiting for the daily check.

    503 update_check_off with RHINVOICE_UPDATE_CHECK=false (and in the demo),
    503 update_check_failed when the release information could not be fetched.
    """
    container.updates.check()
    return UpdateResponse.of(container.updates.status())


@router.post("/updates/install", status_code=status.HTTP_202_ACCEPTED, dependencies=[NOT_IN_DEMO])
def install_update(_user: CurrentUser, container: ContainerDep) -> UpdateResponse:
    """Install the newest release; the program restarts shortly after this answer.

    409 no_update unless the status said "install" (installation without Docker only).
    """
    container.updates.install()
    return UpdateResponse.of(container.updates.status())


@router.post(
    "/updates/setup/download", status_code=status.HTTP_202_ACCEPTED, dependencies=[NOT_IN_DEMO]
)
def download_setup(_user: CurrentUser, container: ContainerDep) -> UpdateResponse:
    """Start downloading the new setup; GET /api/updates tells the progress.

    409 no_setup unless the status offers the setup to download (setup not null).
    """
    container.updates.download_setup()
    return UpdateResponse.of(container.updates.status())


@router.post("/updates/setup/run", status_code=status.HTTP_202_ACCEPTED, dependencies=[NOT_IN_DEMO])
def run_setup(_user: CurrentUser, container: ContainerDep) -> UpdateResponse:
    """Start the downloaded setup; the program closes shortly after this answer.

    409 setup_not_ready unless the setup is downloaded and checked.
    """
    container.updates.run_setup()
    return UpdateResponse.of(container.updates.status())
