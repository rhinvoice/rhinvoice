from datetime import datetime
from typing import Self

from fastapi import APIRouter, status

from rhinvoice.api.dependencies import NOT_IN_DEMO, ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.updates.handlers import UpdateAction, UpdateStatus

router = APIRouter(prefix="/api", tags=["updates"], responses=ERROR_RESPONSES)


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

    @classmethod
    def of(cls, update: UpdateStatus) -> Self:
        return cls(
            current=update.current,
            latest=update.latest,
            action=update.action,
            notes_url=update.notes_url,
            setup_url=update.setup_url,
            checked_at=update.checked_at,
        )


@router.get("/updates")
def get_updates(_user: CurrentUser, container: ContainerDep) -> UpdateResponse:
    """Whether a newer release exists (checked once a day, RHINVOICE_UPDATE_CHECK)."""
    return UpdateResponse.of(container.updates.status())


@router.post("/updates/install", status_code=status.HTTP_202_ACCEPTED, dependencies=[NOT_IN_DEMO])
def install_update(_user: CurrentUser, container: ContainerDep) -> UpdateResponse:
    """Install the newest release; the program restarts shortly after this answer.

    409 no_update unless the status said "install" (installation without Docker only).
    """
    container.updates.install()
    return UpdateResponse.of(container.updates.status())
