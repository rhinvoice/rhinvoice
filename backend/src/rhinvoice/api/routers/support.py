"""What a problem report needs; the person copies it and decides where it goes."""

from fastapi import APIRouter

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.support.handlers import Installation

router = APIRouter(prefix="/api", tags=["support"], responses=ERROR_RESPONSES)


class SupportReportResponse(ApiModel):
    version: str
    system: str
    """The operating system as people know it, e.g. "Windows 11 (AMD64)"."""
    installation: Installation
    """desktop: the program for Windows and Mac, with its log; server: Docker, whose log
    is read with docker compose logs app."""
    log: str | None
    """The last lines of the program's log; None on a server."""


@router.get("/support/report")
def get_support_report(_user: CurrentUser, container: ContainerDep) -> SupportReportResponse:
    """Give the version, the system and the end of the log for a problem report; sends nothing."""
    report = container.support.report()
    return SupportReportResponse(
        version=report.version,
        system=report.system,
        installation=report.installation,
        log=report.log,
    )
