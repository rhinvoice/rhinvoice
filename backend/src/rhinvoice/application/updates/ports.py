"""Where releases are announced, and what can install one (ADR 0022)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class PackageFile:
    """An app package of the installation without Docker, for one platform."""

    url: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class Release:
    version: str
    notes_url: str
    runtime: int
    """The runtime generation its app packages need at least."""
    packages: Mapping[str, PackageFile] = field(default_factory=dict[str, PackageFile])
    """App packages by platform, e.g. "windows-x64"."""
    setups: Mapping[str, str] = field(default_factory=dict[str, str])
    """Setup downloads by platform, for runtimes too old for the packages."""
    setup_files: Mapping[str, PackageFile] = field(default_factory=dict[str, PackageFile])
    """The same setups with size and SHA-256, so the program can download and check one
    itself (ADR 0031); releases before ADR 0031 have none."""


class ReleaseFeed(Protocol):
    def latest(self) -> Release | None:
        """Return the newest release; None when it cannot be known (offline, bad signature)."""
        ...


class UpdateInstaller(Protocol):
    """The installation without Docker: it can put a newer app package in place."""

    platform: str
    """Its app packages in release.json, e.g. "windows-x64"."""
    setup: str
    """Its setup in release.json: the platform, "-beta" added for Rhinvoice Beta (ADR 0030)."""
    runtime: int
    """The generation of the installed runtime."""

    def install(self, release: Release) -> None:
        """Download and check the release's package, put it in place and restart."""
        ...

    def failed(self, version: str) -> bool:
        """Tell whether ``version`` was installed here, did not start and was taken back."""
        ...


class SetupState(StrEnum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    READY = "ready"
    """Downloaded and checked: it can be run."""
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SetupProgress:
    state: SetupState = SetupState.IDLE
    version: str | None = None
    """The release whose setup it is."""
    received: int = 0
    total: int = 0
    """Bytes."""


class SetupInstaller(Protocol):
    """The installation without Docker: it can download a new setup and hand over to it."""

    def download(self, version: str, setup: PackageFile) -> None:
        """Start downloading and checking the setup in the background; return at once."""
        ...

    def progress(self) -> SetupProgress:
        """Tell how far the download is."""
        ...

    def run(self) -> None:
        """Start the downloaded setup and close the program, which the setup then replaces."""
        ...
