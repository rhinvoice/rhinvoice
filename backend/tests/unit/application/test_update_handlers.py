"""Whether a newer Rhinvoice exists, and what the installation can do about it (ADR 0022)."""

from dataclasses import replace

import pytest

from rhinvoice.application.errors import ConflictError, UnavailableError
from rhinvoice.application.updates.handlers import (
    UpdateAction,
    UpdateHandlers,
    UpdateStatus,
    follows,
    is_newer,
)
from rhinvoice.application.updates.ports import (
    PackageFile,
    Release,
    SetupProgress,
    SetupState,
)
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
    setup = "windows-x64"
    runtime = 1

    def __init__(self, *failures: str) -> None:
        self.installed: list[Release] = []
        self.failures = set(failures)

    def install(self, release: Release) -> None:
        self.installed.append(release)

    def failed(self, version: str) -> bool:
        return version in self.failures


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


@pytest.mark.parametrize(
    ("tag", "version", "follows_it"),
    [
        ("latest", "0.7.0", True),
        ("0.7.0", "0.7.0", True),
        ("0.7", "0.7.0", True),
        ("0", "0.7.0", True),
        ("0.6", "0.7.0", False),
        ("0.6.2", "0.7.0", False),
        ("0.7.0-rc.1", "0.7.0", False),
        ("0.7.", "0.7.0", False),
        ("", "0.7.0", False),
    ],
)
def test_an_image_tag_follows_the_releases_it_leads_to(
    tag: str, version: str, follows_it: bool
) -> None:
    assert follows(tag, version) is follows_it


@pytest.mark.parametrize(
    ("tag", "pinned"), [("latest", False), ("0.7", False), ("0.6.2", True), (None, None)]
)
def test_a_server_installation_is_told_whether_env_holds_it_back(
    tag: str | None, pinned: bool | None
) -> None:
    updates = UpdateHandlers(Feed(RELEASE), "0.6.2", FixedClock(NOW), image_tag=tag)
    updates.refresh()
    assert updates.status().pinned is pinned


def test_the_image_tag_only_matters_for_a_server_installation() -> None:
    desktop = UpdateHandlers(
        Feed(RELEASE), "0.6.2", FixedClock(NOW), Installer(), image_tag="0.6.2"
    )
    desktop.refresh()
    current = UpdateHandlers(Feed(RELEASE), "0.7.0", FixedClock(NOW), image_tag="0.6.2")
    current.refresh()
    unchecked = UpdateHandlers(Feed(RELEASE), "0.6.2", FixedClock(NOW), image_tag="0.6.2")
    assert desktop.status().pinned is None
    assert current.status().pinned is None
    assert unchecked.status().pinned is None


def test_before_the_first_check_nothing_is_known() -> None:
    assert handlers(RELEASE).status() == UpdateStatus(
        current="0.6.2",
        latest=None,
        action=UpdateAction.NONE,
        notes_url=None,
        setup_url=None,
        checked_at=None,
        failed=False,
        can_check=True,
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
        failed=False,
        can_check=True,
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
    installer.setup = "macos-arm64"
    updates = handlers(RELEASE, installer=installer)
    updates.refresh()
    status = updates.status()
    assert status.action is UpdateAction.SETUP
    assert status.setup_url is None


def test_rhinvoice_beta_is_led_to_its_own_setup_only() -> None:
    """ADR 0030: the released setup would install Rhinvoice, not a second Rhinvoice Beta."""
    installer = Installer()
    installer.setup = "windows-x64-beta"
    beta_setup = "https://example.org/Rhinvoice-Beta-Setup-Windows.exe"
    with_beta = replace(
        RELEASE, runtime=2, setups={**RELEASE.setups, "windows-x64-beta": beta_setup}
    )
    updates = handlers(with_beta, installer=installer)
    updates.refresh()
    assert updates.status().setup_url == beta_setup
    updates = handlers(replace(RELEASE, runtime=2), installer=installer)
    updates.refresh()
    assert updates.status().setup_url is None


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
    assert updates.status().can_check is False
    with raises_exactly(UnavailableError, "the update check is switched off") as refused:
        updates.check()
    assert refused.value.code == "update_check_off"


def test_a_check_on_request_asks_the_feed_at_once() -> None:
    feed = Feed(RELEASE)
    updates = UpdateHandlers(feed, "0.6.2", FixedClock(NOW), Installer())
    updates.check()
    assert feed.asked == 1
    assert updates.status().latest == "0.7.0"
    assert updates.status().checked_at == NOW


def test_a_check_on_request_tells_when_the_feed_did_not_answer() -> None:
    updates = handlers(RELEASE, None)
    updates.refresh()
    message = "the information about new releases could not be fetched"
    with raises_exactly(UnavailableError, message) as refused:
        updates.check()
    assert refused.value.code == "update_check_failed"
    assert updates.status().latest == "0.7.0"


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
    with raises_exactly(ConflictError, "there is no update to install here") as refused:
        updates.install()
    assert refused.value.code == "no_update"
    assert installer is None or installer.installed == []


def test_nothing_is_installed_before_the_first_check() -> None:
    installer = Installer()
    with raises_exactly(ConflictError, "there is no update to install here"):
        handlers(RELEASE, installer=installer).install()
    assert installer.installed == []


def test_an_update_that_was_taken_back_is_not_offered_again() -> None:
    installer = Installer("0.7.0")
    updates = handlers(RELEASE, installer=installer)
    updates.refresh()
    status = updates.status()
    assert (status.action, status.failed, status.latest) == (UpdateAction.NONE, True, "0.7.0")
    with raises_exactly(ConflictError, "there is no update to install here"):
        updates.install()
    assert installer.installed == []


def test_a_server_installation_never_counts_a_release_as_failed() -> None:
    updates = handlers(RELEASE)
    updates.refresh()
    assert not updates.status().failed


SETUP = PackageFile(url="https://example.org/Rhinvoice-Setup-Windows.exe", sha256="cd" * 32, size=9)
NEEDS_SETUP = replace(RELEASE, runtime=2, setup_files={"windows-x64": SETUP})


class SetupInstaller:
    def __init__(self, progress: SetupProgress | None = None) -> None:
        self.downloads: list[tuple[str, PackageFile]] = []
        self.runs = 0
        self.current = progress or SetupProgress()

    def download(self, version: str, setup: PackageFile) -> None:
        self.downloads.append((version, setup))

    def progress(self) -> SetupProgress:
        return self.current

    def run(self) -> None:
        self.runs += 1


def setup_handlers(
    release: Release = NEEDS_SETUP,
    setup_installer: SetupInstaller | None = None,
    installer: Installer | None = None,
) -> UpdateHandlers:
    updates = UpdateHandlers(
        Feed(release), "0.6.2", FixedClock(NOW), installer or Installer(), setup_installer
    )
    updates.refresh()
    return updates


def test_the_program_downloads_the_setup_it_needs_and_runs_it() -> None:
    """ADR 0031: no browser, no download folder, the setup checked like a package."""
    setup_installer = SetupInstaller()
    updates = setup_handlers(setup_installer=setup_installer)
    assert updates.status().action is UpdateAction.SETUP
    assert updates.status().setup == SetupProgress()
    updates.download_setup()
    assert setup_installer.downloads == [("0.7.0", SETUP)]
    setup_installer.current = SetupProgress(SetupState.DOWNLOADING, "0.7.0", 4, 9)
    assert updates.status().setup == SetupProgress(SetupState.DOWNLOADING, "0.7.0", 4, 9)
    with raises_exactly(ConflictError, "the setup is not downloaded yet") as refused:
        updates.run_setup()
    assert refused.value.code == "setup_not_ready"
    setup_installer.current = SetupProgress(SetupState.READY, "0.7.0", 9, 9)
    updates.run_setup()
    assert setup_installer.runs == 1


def test_the_setup_of_an_older_release_is_not_this_ones() -> None:
    setup_installer = SetupInstaller(SetupProgress(SetupState.READY, "0.6.9", 9, 9))
    updates = setup_handlers(setup_installer=setup_installer)
    assert updates.status().setup == SetupProgress()
    with raises_exactly(ConflictError, "the setup is not downloaded yet"):
        updates.run_setup()
    assert setup_installer.runs == 0


def failed_installer() -> Installer:
    return Installer("0.7.0")


def beta_installer() -> Installer:
    installer = Installer()
    installer.setup = "windows-x64-beta"
    return installer


@pytest.mark.parametrize(
    ("release", "setup_installer", "installer"),
    [
        (replace(NEEDS_SETUP, setup_files={}), SetupInstaller(), None),  # before 0.8.2
        (NEEDS_SETUP, None, None),  # a server installation, or no helper for this system
        (replace(NEEDS_SETUP, runtime=1), SetupInstaller(), None),  # the package does
        (replace(NEEDS_SETUP, version="0.6.2"), SetupInstaller(), None),  # nothing newer
        (NEEDS_SETUP, SetupInstaller(), failed_installer()),  # taken back
        (NEEDS_SETUP, SetupInstaller(), beta_installer()),  # Rhinvoice's, not Beta's
    ],
)
def test_a_setup_is_only_downloaded_when_it_is_needed_and_known(
    release: Release, setup_installer: SetupInstaller | None, installer: Installer | None
) -> None:
    updates = setup_handlers(release, setup_installer, installer)
    assert updates.status().setup is None
    with raises_exactly(ConflictError, "there is no setup to download here") as refused:
        updates.download_setup()
    assert refused.value.code == "no_setup"
    with raises_exactly(ConflictError, "the setup is not downloaded yet"):
        updates.run_setup()
    assert setup_installer is None or (setup_installer.downloads, setup_installer.runs) == ([], 0)


def test_nothing_is_downloaded_before_the_first_check() -> None:
    setup_installer = SetupInstaller()
    updates = UpdateHandlers(
        Feed(NEEDS_SETUP), "0.6.2", FixedClock(NOW), Installer(), setup_installer
    )
    with raises_exactly(ConflictError, "there is no setup to download here"):
        updates.download_setup()
    assert setup_installer.downloads == []
