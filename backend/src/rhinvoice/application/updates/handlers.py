"""Whether a newer Rhinvoice exists, and what the installation can do about it (ADR 0022).

A server installation (Docker) is told the release; it updates with its own commands.
The installation without Docker installs the release's app package with one click, unless
the package needs a newer runtime: then the setup has to be run, which the program
downloads, checks and starts itself (ADR 0031).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.application.errors import ConflictError, UnavailableError
from rhinvoice.application.updates.ports import SetupProgress, SetupState

if TYPE_CHECKING:
    from datetime import datetime

    from rhinvoice.application.updates.ports import (
        PackageFile,
        Release,
        ReleaseFeed,
        SetupInstaller,
        UpdateInstaller,
    )
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
    failed: bool = False
    """The newest release was installed here, did not start and was taken back: the
    version that ran before runs again, and the release is not offered again."""
    can_check: bool = False
    """Someone may ask for a check now; False with the check switched off."""
    setup: SetupProgress | None = None
    """The new setup as the program downloads it; None when it cannot (ADR 0031)."""
    pinned: bool | None = None
    """With action command: True when the image tag in .env (RHINVOICE_VERSION) holds the
    server below the release, so it has to change before the pull; False when the pull
    alone brings it (latest, or 0.8 for 0.8.3); None when the tag is not known."""


def follows(tag: str, version: str) -> bool:
    """Tell whether the image ``tag`` leads to ``version`` (latest, 0.8 and 0.8.3 to 0.8.3)."""
    return tag in {"latest", version} or version.startswith(f"{tag}.")


def is_newer(
    version: str,
    current: str,
    candidate: int | None = None,
    current_candidate: int | None = None,
) -> bool:
    """Tell whether ``version`` is later than ``current`` (0.10.0 after 0.9.1).

    Of one version, a later release candidate counts only when both candidates are known
    (Rhinvoice Beta, ADR 0035): 0.8.4-rc.3 after 0.8.4-rc.2. The release promoted from a
    candidate carries its candidate, so it is not offered to the one that runs it already.
    """
    try:
        new, old = tuple(map(int, version.split("."))), tuple(map(int, current.split(".")))
    except ValueError:
        return False
    if new != old:
        return new > old
    return candidate is not None and current_candidate is not None and candidate > current_candidate


def build_name(version: str, candidate: int | None) -> str:
    """Name a version as built from a release candidate: 0.8.4-rc.3 (ADR 0035)."""
    return version if candidate is None else f"{version}-rc.{candidate}"


class UpdateHandlers:
    def __init__(  # noqa: PLR0913 - what decides the update (keyword for the image tag)
        self,
        feed: ReleaseFeed | None,
        current: str,
        clock: Clock,
        installer: UpdateInstaller | None = None,
        setup_installer: SetupInstaller | None = None,
        *,
        image_tag: str | None = None,
    ) -> None:
        """``feed`` None: the check is switched off (RHINVOICE_UPDATE_CHECK=false).

        ``image_tag``: the tag a server installation's image was started with
        (RHINVOICE_VERSION); None when not known.
        """
        self._feed = feed
        self._current = current
        self._clock = clock
        self._installer = installer
        self._setup_installer = setup_installer
        self._image_tag = image_tag
        # Replaced as one tuple: requests read it while the background check writes it.
        self._known: tuple[Release | None, datetime | None] = (None, None)

    def refresh(self) -> None:
        """Ask the feed (at the start and once a day); keep what was known when it fails."""
        if self._feed is None:
            return
        release = self._feed.latest()
        if release is not None:
            self._known = (release, self._clock.now())

    def check(self) -> None:
        """Ask the feed now, on request; tell when it is switched off or did not answer."""
        if self._feed is None:
            msg = "the update check is switched off"
            raise UnavailableError(msg, code="update_check_off")
        release = self._feed.latest()
        if release is None:
            msg = "the information about new releases could not be fetched"
            raise UnavailableError(msg, code="update_check_failed")
        self._known = (release, self._clock.now())

    def status(self) -> UpdateStatus:
        release, checked_at = self._known
        failed = (
            release is not None and self._installer is not None and self._installer.failed(release)
        )
        if release is None or failed or not self._is_newer(release):
            action = UpdateAction.NONE
        elif self._installer is None:
            action = UpdateAction.COMMAND
        else:
            action = _desktop_action(release, self._installer)
        setup_url = None
        if release is not None and self._installer is not None:
            setup_url = release.setups.get(self._installer.setup)
        candidate = self._candidate()
        return UpdateStatus(
            current=build_name(self._current, candidate),
            # Rhinvoice Beta tells candidates of one version apart; Rhinvoice never sees one.
            latest=None
            if release is None
            else build_name(release.version, None if candidate is None else release.candidate),
            action=action,
            notes_url=None if release is None else release.notes_url,
            setup_url=setup_url,
            checked_at=checked_at,
            failed=failed,
            can_check=self._feed is not None,
            setup=None if (offer := self._setup_offer(release)) is None else _progress(offer),
            pinned=(
                None
                if release is None or action is not UpdateAction.COMMAND or self._image_tag is None
                else not follows(self._image_tag, release.version)
            ),
        )

    def install(self) -> None:
        release, _ = self._known
        installer = self._installer
        if (
            release is None
            or installer is None
            or not self._is_newer(release)
            or installer.failed(release)
            or _desktop_action(release, installer) is not UpdateAction.INSTALL
        ):
            raise ConflictError("there is no update to install here", code="no_update")
        installer.install(release)

    def download_setup(self) -> None:
        """Start downloading the setup the status asks for (ADR 0031)."""
        offer = self._setup_offer(self._known[0])
        if offer is None:
            raise ConflictError("there is no setup to download here", code="no_setup")
        release, setup, setup_installer = offer
        setup_installer.download(release.version, setup)

    def run_setup(self) -> None:
        """Hand over to the downloaded setup: the program closes, the setup installs."""
        offer = self._setup_offer(self._known[0])
        if offer is None or _progress(offer).state is not SetupState.READY:
            raise ConflictError("the setup is not downloaded yet", code="setup_not_ready")
        offer[2].run()

    def _candidate(self) -> int | None:
        return None if self._installer is None else self._installer.candidate

    def _is_newer(self, release: Release) -> bool:
        return is_newer(release.version, self._current, release.candidate, self._candidate())

    def _setup_offer(
        self, release: Release | None
    ) -> tuple[Release, PackageFile, SetupInstaller] | None:
        """Return the release's setup if it is needed and the program can install it itself."""
        installer = self._installer
        setup_installer = self._setup_installer
        if release is None or installer is None or setup_installer is None:
            return None
        setup = release.setup_files.get(installer.setup)
        if (
            setup is None
            or not self._is_newer(release)
            or installer.failed(release)
            or _desktop_action(release, installer) is not UpdateAction.SETUP
        ):
            return None
        return release, setup, setup_installer


def _progress(offer: tuple[Release, PackageFile, SetupInstaller]) -> SetupProgress:
    release, _, setup_installer = offer
    progress = setup_installer.progress()
    # A setup of another release (an older download) is not this one's.
    return progress if progress.version == release.version else SetupProgress()


def _desktop_action(release: Release, installer: UpdateInstaller) -> UpdateAction:
    """Install the release's package, unless there is none for this platform and runtime."""
    if installer.platform not in release.packages or release.runtime > installer.runtime:
        return UpdateAction.SETUP
    return UpdateAction.INSTALL
