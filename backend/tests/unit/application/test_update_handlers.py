"""Whether a newer Rhinvoice exists, and what the installation can do about it (ADR 0022)."""

from dataclasses import replace

import pytest

from rhinvoice.application.errors import ConflictError
from rhinvoice.application.updates.handlers import (
    UpdateAction,
    UpdateHandlers,
    UpdateStatus,
    is_newer,
)
from rhinvoice.application.updates.ports import PackageFile, Release
from rhinvoice.domain.shared.clock import FixedClock
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW

PACKAGE = PackageFile(url="https://example.org/app.zip", sha256="ab" * 32, size=1234)
RELEASE = Release(
    version="0.7.0",
    notes_url="https://example.org/releases/v0.7.0",
    runtime=1,
    packages={"windows-x64": PACKAGE},
    setups={"windows-x64": "https://example.org/Rhinvoice-Setup-0.7.0.exe"},
)


class Feed:
    def __init__(self, *releases: Release | None) -> None:
        self.releases = list(releases)
        self.asked = 0

    def latest(self) -> Release | None:
        self.asked += 1
        return self.releases.pop(0)


class Installer:
    platform = "windows-x64"
    runtime = 1

    def __init__(self) -> None:
        self.installed: list[Release] = []

    def install(self, release: Release) -> None:
        self.installed.append(release)


def handlers(
    *releases: Release | None, installer: Installer | None = None, current: str = "0.6.2"
) -> UpdateHandlers:
    return UpdateHandlers(Feed(*releases), current, FixedClock(NOW), installer)


@pytest.mark.parametrize(
    ("candidate", "current", "newer"),
    [
        ("0.7.0", "0.6.2", True),
        ("0.10.0", "0.9.9", True),
        ("1.0", "0.99.0", True),
        ("0.6.2", "0.6.2", False),
        ("0.6.1", "0.6.2", False),
        ("0.6.2.1", "0.6.2", True),
        ("v0.7.0", "0.6.2", False),
        ("0.7.0", "dev", False),
        ("", "0.6.2", False),
    ],
)
def test_versions_are_compared_by_their_numbers(candidate: str, current: str, newer: bool) -> None:
    assert is_newer(candidate, current) is newer


def test_before_the_first_check_nothing_is_known() -> None:
    assert handlers(RELEASE).status() == UpdateStatus(
        current="0.6.2",
        latest=None,
        action=UpdateAction.NONE,
        notes_url=None,
        setup_url=None,
        checked_at=None,
    )


def test_a_server_installation_is_told_the_command() -> None:
    updates = handlers(RELEASE)
    updates.refresh()
    assert updates.status() == UpdateStatus(
        current="0.6.2",
        latest="0.7.0",
        action=UpdateAction.COMMAND,
        notes_url="https://example.org/releases/v0.7.0",
        setup_url=None,
        checked_at=NOW,
    )


def test_the_desktop_installs_a_package_for_its_platform() -> None:
    installer = Installer()
    updates = handlers(RELEASE, installer=installer)
    updates.refresh()
    assert updates.status().action is UpdateAction.INSTALL
    updates.install()
    assert installer.installed == [RELEASE]


def test_a_package_that_needs_a_newer_runtime_needs_the_setup() -> None:
    updates = handlers(replace(RELEASE, runtime=2), installer=Installer())
    updates.refresh()
    status = updates.status()
    assert status.action is UpdateAction.SETUP
    assert status.setup_url == "https://example.org/Rhinvoice-Setup-0.7.0.exe"


def test_a_release_without_a_package_for_this_platform_needs_the_setup() -> None:
    installer = Installer()
    installer.platform = "macos-arm64"
    updates = handlers(RELEASE, installer=installer)
    updates.refresh()
    status = updates.status()
    assert status.action is UpdateAction.SETUP
    assert status.setup_url is None


def test_the_running_version_or_an_older_one_offers_nothing() -> None:
    updates = handlers(RELEASE, installer=Installer(), current="0.7.0")
    updates.refresh()
    assert updates.status().action is UpdateAction.NONE
    assert updates.status().latest == "0.7.0"


def test_an_unreachable_feed_keeps_what_was_known() -> None:
    updates = handlers(RELEASE, None)
    updates.refresh()
    updates.refresh()  # offline now
    assert updates.status().latest == "0.7.0"


def test_without_a_feed_nothing_is_ever_checked() -> None:
    updates = UpdateHandlers(None, "0.6.2", FixedClock(NOW), Installer())
    updates.refresh()
    assert updates.status().action is UpdateAction.NONE
    assert updates.status().checked_at is None


@pytest.mark.parametrize(
    ("installer", "release"),
    [
        (None, RELEASE),  # a server installation updates with its own commands
        (Installer(), replace(RELEASE, version="0.6.2")),  # nothing newer
        (Installer(), replace(RELEASE, runtime=2)),  # needs the setup
    ],
)
def test_only_an_offered_package_is_installed(
    installer: Installer | None, release: Release
) -> None:
    updates = handlers(release, installer=installer)
    updates.refresh()
    with raises_exactly(ConflictError, "there is no update to install here"):
        updates.install()
    assert installer is None or installer.installed == []
