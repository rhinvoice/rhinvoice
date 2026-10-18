"""Installing a new setup from within the program (ADR 0031)."""

import hashlib
import subprocess
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import pytest

from rhinvoice.application.errors import ConflictError
from rhinvoice.application.updates.ports import PackageFile, SetupProgress, SetupState
from rhinvoice.desktop import setup as desktop_setup
from rhinvoice.desktop.edition import BETA, STABLE
from rhinvoice.desktop.setup import (
    MACOS_SCRIPT,
    WINDOWS_ARGUMENTS,
    SetupDownloader,
    helper_command,
    mark_running,
    start_detached,
)
from tests.helpers import raises_exactly

URL = "https://github.com/rhinvoice/rhinvoice/releases/download/v0.9.0/Rhinvoice-Setup-Windows.exe"
CONTENT = b"MZ" + b"setup" * 1000


def setup_file(
    content: bytes = CONTENT, *, url: str = URL, sha256: str | None = None
) -> PackageFile:
    return PackageFile(url, sha256 or hashlib.sha256(content).hexdigest(), len(CONTENT))


def github(
    content: bytes = CONTENT, status: int = 200
) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == URL
        return httpx.Response(status, content=content)

    return handle


class Surroundings:
    """What the downloader starts and closes, recorded."""

    def __init__(self) -> None:
        self.started: list[list[str]] = []
        self.closed = threading.Event()

    def command(self, setup: Path) -> list[str]:
        return [str(setup), "/SILENT"]

    def start(self, command: Sequence[str]) -> None:
        self.started.append(list(command))

    def close(self) -> None:
        self.closed.set()


def downloader(
    data: Path,
    handle: Callable[[httpx.Request], httpx.Response],
    surroundings: Surroundings,
    current: str = "0.8.1",
) -> SetupDownloader:
    client = httpx.Client(transport=httpx.MockTransport(handle))
    return SetupDownloader(
        data,
        current,
        surroundings.command,
        surroundings.close,
        client=client,
        start=surroundings.start,
        close_delay=0,
    )


def wait_until_done(setup: SetupDownloader) -> SetupProgress:
    for _ in range(500):
        progress = setup.progress()
        if progress.state is not SetupState.DOWNLOADING:
            return progress
        threading.Event().wait(0.01)
    raise AssertionError(setup.progress())


def test_the_setup_is_downloaded_checked_and_run_after_the_program_closes(tmp_path: Path) -> None:
    surroundings = Surroundings()
    setup = downloader(tmp_path, github(), surroundings)
    assert setup.progress() == SetupProgress()
    setup.download("0.9.0", setup_file())
    assert wait_until_done(setup) == SetupProgress(
        SetupState.READY, "0.9.0", len(CONTENT), len(CONTENT)
    )
    saved = tmp_path / "app" / "setup" / "0.9.0" / "Rhinvoice-Setup-Windows.exe"
    assert saved.read_bytes() == CONTENT
    assert not saved.with_name(saved.name + ".partial").exists()
    setup.run()
    assert surroundings.started == [[str(saved), "/SILENT"]]
    assert surroundings.closed.wait(5)


def test_a_setup_that_is_downloading_or_ready_is_not_downloaded_again(tmp_path: Path) -> None:
    asked: list[str] = []

    def counted(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return github()(request)

    setup = downloader(tmp_path, counted, Surroundings())
    setup.download("0.9.0", setup_file())
    setup.download("0.9.0", setup_file())
    wait_until_done(setup)
    setup.download("0.9.0", setup_file())
    assert asked == [URL]


@pytest.mark.parametrize(
    ("handle", "announced"),
    [
        (github(), setup_file(sha256="00" * 32)),
        (github(CONTENT[:-1]), setup_file()),
        (github(CONTENT + b"more"), setup_file()),
        (github(status=404), setup_file()),
        (github(), setup_file(url="https://github.com/x/download/v0.9.0/setup.zip")),
        (github(), setup_file(url="https://github.com/x/download/v0.9.0/.exe")),
    ],
)
def test_anything_but_the_released_setup_fails_and_is_never_run(
    tmp_path: Path,
    handle: Callable[[httpx.Request], httpx.Response],
    announced: PackageFile,
) -> None:
    surroundings = Surroundings()
    setup = downloader(tmp_path, handle, surroundings)
    setup.download("0.9.0", announced)
    assert wait_until_done(setup).state is SetupState.FAILED
    with raises_exactly(ConflictError, "the setup is not downloaded yet") as refused:
        setup.run()
    assert refused.value.code == "setup_not_ready"
    assert surroundings.started == []
    assert not surroundings.closed.is_set()
    folder = tmp_path / "app" / "setup" / "0.9.0"
    assert not folder.exists() or [path.name for path in folder.iterdir()] == []


def test_a_failed_download_can_be_tried_again(tmp_path: Path) -> None:
    answers = [httpx.Response(503), httpx.Response(200, content=CONTENT)]
    setup = downloader(tmp_path, lambda _request: answers.pop(0), Surroundings())
    setup.download("0.9.0", setup_file())
    assert wait_until_done(setup).state is SetupState.FAILED
    setup.download("0.9.0", setup_file())
    assert wait_until_done(setup).state is SetupState.READY


def test_a_newer_setup_replaces_an_older_download(tmp_path: Path) -> None:
    older = tmp_path / "app" / "setup" / "0.8.9"
    older.mkdir(parents=True)
    (older / "Rhinvoice-Setup-Windows.exe").write_bytes(b"old")
    setup = downloader(tmp_path, github(), Surroundings())
    setup.download("0.9.0", setup_file())
    wait_until_done(setup)
    assert sorted(path.name for path in (tmp_path / "app" / "setup").iterdir()) == ["0.9.0"]


def test_setups_installed_by_now_are_removed_at_the_start(tmp_path: Path) -> None:
    folder = tmp_path / "app" / "setup"
    for version in ("0.8.0", "0.8.1", "0.9.0"):
        (folder / version).mkdir(parents=True)
    downloader(tmp_path, github(), Surroundings(), current="0.8.1")
    assert sorted(path.name for path in folder.iterdir()) == ["0.9.0"]


def test_without_any_setup_the_start_removes_nothing(tmp_path: Path) -> None:
    downloader(tmp_path, github(), Surroundings())
    assert not (tmp_path / "app").exists()


def test_by_default_the_setup_comes_from_the_internet(tmp_path: Path) -> None:
    surroundings = Surroundings()
    built = SetupDownloader(tmp_path, "0.8.1", surroundings.command, surroundings.close)
    assert built.progress() == SetupProgress()


def test_on_windows_the_setup_itself_waits_for_the_program(tmp_path: Path) -> None:
    setup = tmp_path / "Rhinvoice-Setup-Windows.exe"
    assert helper_command(
        setup, system="Windows", data=tmp_path / "data", install=tmp_path / "install"
    ) == [
        str(setup),
        *WINDOWS_ARGUMENTS,
    ]
    assert "/FROMRHINVOICE" in WINDOWS_ARGUMENTS
    assert "/SILENT" in WINDOWS_ARGUMENTS


def test_on_a_mac_a_script_replaces_the_app_once_the_session_lock_is_free(tmp_path: Path) -> None:
    image = tmp_path / "Rhinvoice-macOS.dmg"
    install = Path("/Applications/Rhinvoice.app/Contents/Resources")
    data = tmp_path / "data"
    assert helper_command(image, system="Darwin", data=data, install=install) == [
        "/bin/sh",
        "-c",
        MACOS_SCRIPT,
        "rhinvoice-setup",
        str(data / "app" / "session.lock"),
        str(image),
        "/Applications/Rhinvoice.app",
    ]


def test_the_helper_outlives_the_program(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[tuple[Sequence[str], dict[str, object]]] = []

    def popen(command: Sequence[str], **options: object) -> None:
        started.append((command, options))

    monkeypatch.setattr(subprocess, "Popen", popen)
    start_detached(["/bin/sh", "-c", "true"])
    [(command, options)] = started
    assert command == ["/bin/sh", "-c", "true"]
    assert options["start_new_session"] is True
    assert options["creationflags"] == desktop_setup.DETACHED
    assert options["stdin"] == subprocess.DEVNULL


def test_only_windows_needs_a_mutex() -> None:
    assert mark_running("RhinvoiceRunning") is None


def test_each_edition_has_its_own_mutex() -> None:
    """The names desktop/windows/rhinvoice.iss waits for."""
    assert (STABLE.mutex, BETA.mutex) == ("RhinvoiceRunning", "RhinvoiceBetaRunning")
    iss = (Path(__file__).parents[4] / "desktop" / "windows" / "rhinvoice.iss").read_text(
        "utf-8-sig"
    )
    assert '#define RunningMutex "RhinvoiceRunning"' in iss
    assert '#define RunningMutex "RhinvoiceBetaRunning"' in iss
