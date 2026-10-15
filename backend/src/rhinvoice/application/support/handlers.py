"""What a problem report carries: the version, the system and the end of the log.

Nothing is sent anywhere: the person copies the report and decides where it goes. Only
the installation without Docker has a log file here; a server keeps its log with Docker.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rhinvoice.application.support.ports import ProgramLog

LOG_LINES = 200
"""Enough to show what led to a problem, short enough to paste into a report."""


class Installation(StrEnum):
    DESKTOP = "desktop"
    """The program for Windows and Mac: its log comes with the report."""
    SERVER = "server"
    """Docker: the log is read on the server (docker compose logs app)."""


@dataclass(frozen=True, slots=True)
class SupportReport:
    version: str
    system: str
    installation: Installation
    log: str | None
    """The last lines of the program's log; None on a server."""


class SupportHandlers:
    def __init__(self, version: str, system: str, log: ProgramLog | None) -> None:
        """``log`` None: a server, whose log stays with Docker."""
        self._version = version
        self._system = system
        self._log = log

    def report(self) -> SupportReport:
        if self._log is None:
            return SupportReport(self._version, self._system, Installation.SERVER, None)
        log = self._log.last_lines(LOG_LINES)
        return SupportReport(self._version, self._system, Installation.DESKTOP, log)
