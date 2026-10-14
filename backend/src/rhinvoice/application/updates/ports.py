"""Where releases are announced, and what can install one (ADR 0022)."""

from __future__ import annotations

from dataclasses import dataclass, field
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


class ReleaseFeed(Protocol):
    def latest(self) -> Release | None:
        """Return the newest release; None when it cannot be known (offline, bad signature)."""
        ...


class UpdateInstaller(Protocol):
    """The installation without Docker: it can put a newer app package in place."""

    platform: str
    runtime: int
    """The generation of the installed runtime."""

    def install(self, release: Release) -> None:
        """Download and check the release's package, put it in place and restart."""
        ...

    def failed(self, version: str) -> bool:
        """Tell whether ``version`` was installed here, did not start and was taken back."""
        ...
