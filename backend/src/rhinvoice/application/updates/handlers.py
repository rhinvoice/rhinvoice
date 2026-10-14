"""Whether a newer Rhinvoice exists, and what the installation can do about it (ADR 0022).

A server installation (Docker) is told the release; it updates with its own commands.
The installation without Docker installs the release's app package with one click, unless
the package needs a newer runtime: then the setup has to be run.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.application.errors import ConflictError

if TYPE_CHECKING:
    from datetime import datetime

    from rhinvoice.application.updates.ports import Release, ReleaseFeed, UpdateInstaller
    from rhinvoice.domain.shared.clock import Clock


class UpdateAction(StrEnum):
    NONE = "none"
    """This is the newest version, or nothing is known."""
    COMMAND = "command"
    """A server installation: the administrator updates it (docker compose pull)."""
    INSTALL = "install"
    """The installation without Docker installs the package itself."""
    SETUP = "setup"
    """The installation without Docker needs a new setup first."""


@dataclass(frozen=True, slots=True)
class UpdateStatus:
    current: str
    latest: str | None
    action: UpdateAction
    notes_url: str | None
    setup_url: str | None
    checked_at: datetime | None


def is_newer(candidate: str, current: str) -> bool:
    """Tell whether ``candidate`` is a later version than ``current`` (0.10.0 after 0.9.1)."""
    try:
        return tuple(map(int, candidate.split("."))) > tuple(map(int, current.split(".")))
    except ValueError:
        return False


class UpdateHandlers:
    def __init__(
        self,
        feed: ReleaseFeed | None,
        current: str,
        clock: Clock,
        installer: UpdateInstaller | None = None,
    ) -> None:
        """``feed`` None: the check is switched off (RHINVOICE_UPDATE_CHECK=false)."""
        self._feed = feed
        self._current = current
        self._clock = clock
        self._installer = installer
        # Replaced as one tuple: requests read it while the background check writes it.
        self._known: tuple[Release | None, datetime | None] = (None, None)

    def refresh(self) -> None:
        """Ask the feed (at the start and once a day); keep what was known when it fails."""
        if self._feed is None:
            return
        release = self._feed.latest()
        if release is not None:
            self._known = (release, self._clock.now())

    def status(self) -> UpdateStatus:
        release, checked_at = self._known
        if release is None or not is_newer(release.version, self._current):
            action = UpdateAction.NONE
        else:
            action = self._action(release)
        setup_url = None
        if release is not None and self._installer is not None:
            setup_url = release.setups.get(self._installer.platform)
        return UpdateStatus(
            current=self._current,
            latest=None if release is None else release.version,
            action=action,
            notes_url=None if release is None else release.notes_url,
            setup_url=setup_url,
            checked_at=checked_at,
        )

    def install(self) -> None:
        release, _ = self._known
        if (
            release is None
            or self._installer is None
            or self.status().action != UpdateAction.INSTALL
        ):
            raise ConflictError("there is no update to install here", code="no_update")
        self._installer.install(release)

    def _action(self, release: Release) -> UpdateAction:
        installer = self._installer
        if installer is None:
            return UpdateAction.COMMAND
        if installer.platform not in release.packages or release.runtime > installer.runtime:
            return UpdateAction.SETUP
        return UpdateAction.INSTALL
