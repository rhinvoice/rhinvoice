"""Installing an update of the installation without Docker (ADR 0022)."""

import hashlib
import io
import json
import signal
import threading
import zipfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

import rhinvoice_boot
from rhinvoice.application.errors import ConflictError, UnavailableError
from rhinvoice.application.updates.ports import PackageFile, Release
from rhinvoice.desktop.updates import (
    BUILD,
    VERIFIED,
    PackageInstaller,
    Restarter,
    platform_name,
    running_candidate,
    verified,
)
from rhinvoice_boot import State, save_state
from tests.helpers import raises_exactly

URL = "https://github.com/rhinvoice/rhinvoice/releases/download/v0.7.0/app.zip"


def archive(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        for name, content in files.items():
            zipped.writestr(name, content)
    return output.getvalue()


PACKAGE = archive({
    "manifest.json": json.dumps({"version": "0.7.0", "runtime": 1}),
    "site-packages/rhinvoice/__init__.py": "",
    "static/index.html": "<!doctype html>",
})  # fmt: skip
MANIFEST_RC_2 = archive(
    {"manifest.json": json.dumps({"version": "0.7.0", "runtime": 1, "candidate": 2})}
)


def release(
    content: bytes = PACKAGE, *, size: int | None = None, sha256: str | None = None
) -> Release:
    package = PackageFile(
        url=URL,
        sha256=sha256 or hashlib.sha256(content).hexdigest(),
        size=len(content) if size is None else size,
    )
    return Release("0.7.0", "https://x", 1, packages={"windows-x64": package})


class Restarts:
    def __init__(self) -> None:
        self.done = threading.Event()

    def __call__(self) -> None:
        self.done.set()


def github(content: bytes, status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == URL
        return httpx.Response(status, content=content)

    return handle


def installer(
    data: Path, handle: Callable[[httpx.Request], httpx.Response], restarts: Restarts
) -> PackageInstaller:
    client = httpx.Client(transport=httpx.MockTransport(handle))
    return PackageInstaller(data, "windows-x64", 1, restarts, client=client, restart_delay=0)


@pytest.mark.parametrize(
    ("system", "machine", "name"),
    [
        ("Windows", "AMD64", "windows-x64"),
        # As sysconfig names the bundled interpreter, also on Windows on ARM (x64 emulated).
        ("Windows", "amd64", "windows-x64"),
        ("Darwin", "arm64", "macos-arm64"),
        ("Darwin", "x86_64", "macos-x64"),
        ("Linux", "aarch64", "linux-arm64"),
    ],
)
def test_platforms_are_named_as_in_the_release(system: str, machine: str, name: str) -> None:
    assert platform_name(system, machine) == name


def test_the_package_is_put_in_place_and_the_program_restarts(tmp_path: Path) -> None:
    restarts = Restarts()
    installer(tmp_path, github(PACKAGE), restarts).install(release())
    package = tmp_path / "app" / "versions" / "0.7.0"
    assert (package / "static" / "index.html").read_text() == "<!doctype html>"
    assert not (tmp_path / "app" / "versions" / "0.7.0.partial").exists()
    assert restarts.done.wait(5)


def test_a_package_already_in_place_is_not_downloaded_again(tmp_path: Path) -> None:
    installer(tmp_path, github(PACKAGE), Restarts()).install(release())
    package = tmp_path / "app" / "versions" / "0.7.0"
    assert (package / VERIFIED).read_text() == hashlib.sha256(PACKAGE).hexdigest() + "\n"

    def nothing(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request)

    restarts = Restarts()
    installer(tmp_path, nothing, restarts).install(release())
    assert restarts.done.wait(5)


@pytest.mark.parametrize(
    "marker",
    [
        None,  # put there by someone else, or by a program before the marker
        "00" * 32 + "\n",  # of another archive
        b"\xff\xfe",
    ],
)
def test_a_folder_of_the_version_that_was_not_verified_is_installed_afresh(
    tmp_path: Path, marker: str | bytes | None
) -> None:
    package = tmp_path / "app" / "versions" / "0.7.0"
    (package / "site-packages").mkdir(parents=True)
    (package / "site-packages" / "planted.pth").write_text("import planted")
    if isinstance(marker, str):
        (package / VERIFIED).write_text(marker)
    elif marker is not None:
        (package / VERIFIED).write_bytes(marker)
    restarts = Restarts()
    installer(tmp_path, github(PACKAGE), restarts).install(release())
    assert not (package / "site-packages" / "planted.pth").exists()
    assert (package / "static" / "index.html").read_text() == "<!doctype html>"
    assert verified(package, release().packages["windows-x64"])
    assert restarts.done.wait(5)


def test_a_folder_that_cannot_be_replaced_stops_the_update(tmp_path: Path) -> None:
    # A file where the package's folder belongs: shutil.rmtree refuses it.
    package = tmp_path / "app" / "versions" / "0.7.0"
    package.parent.mkdir(parents=True)
    package.write_text("in the way")
    restarts = Restarts()
    with pytest.raises(UnavailableError, match="could not be replaced"):
        installer(tmp_path, github(PACKAGE), restarts).install(release())
    assert package.read_text() == "in the way"
    assert sorted(path.name for path in package.parent.iterdir()) == ["0.7.0"]
    assert not restarts.done.is_set()


@pytest.mark.parametrize(
    ("handle", "announced", "message"),
    [
        (
            github(PACKAGE),
            release(sha256="00" * 32),
            "the downloaded update is not the released one",
        ),
        (github(PACKAGE), release(size=10), "the downloaded update is not the released one"),
        (github(PACKAGE[:-5]), release(), "the downloaded update is not the released one"),
        (github(b"", status=404), release(), None),
        (
            github(archive({"../outside.txt": "x"})),
            release(archive({"../outside.txt": "x"})),
            "the update contains an unsafe path: ../outside.txt",
        ),
        (
            github(archive({"C:/Windows/x.dll": "x"})),
            release(archive({"C:/Windows/x.dll": "x"})),
            "the update contains an unsafe path: C:/Windows/x.dll",
        ),
        (
            github(archive({"static/index.html": "x"})),
            release(archive({"static/index.html": "x"})),
            "the update has no valid manifest.json",
        ),
        (
            github(archive({"manifest.json": '{"version": "0.6.0", "runtime": 1}'})),
            release(archive({"manifest.json": '{"version": "0.6.0", "runtime": 1}'})),
            "the update's manifest.json does not match the release",
        ),
        (
            # Built as another candidate than the release says (ADR 0035).
            github(MANIFEST_RC_2),
            replace(release(MANIFEST_RC_2), candidate=3),
            "the update's manifest.json does not match the release",
        ),
        (
            github(archive({"manifest.json": "[]"})),
            release(archive({"manifest.json": "[]"})),
            "the update has no valid manifest.json",
        ),
    ],
)
def test_anything_but_the_released_package_is_refused(
    tmp_path: Path,
    handle: Callable[[httpx.Request], httpx.Response],
    announced: Release,
    message: str | None,
) -> None:
    restarts = Restarts()
    with pytest.raises(UnavailableError) as raised:
        installer(tmp_path, handle, restarts).install(announced)
    if message is not None:
        assert str(raised.value) == message
    else:
        assert str(raised.value).startswith("the update could not be downloaded: ")
    versions = tmp_path / "app" / "versions"
    assert list(versions.iterdir()) == []
    assert not (tmp_path / "outside.txt").exists()
    assert not restarts.done.is_set()


def test_by_default_the_package_comes_from_the_internet(tmp_path: Path) -> None:
    built = PackageInstaller(tmp_path, "windows-x64", 1, Restarts())
    assert (built.platform, built.runtime) == ("windows-x64", 1)


def test_a_restart_closes_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[str] = []
    signals: list[int] = []
    monkeypatch.setattr(signal, "raise_signal", signals.append)
    restarter = Restarter()
    restarter.use_window(lambda: closed.append("window"))
    restarter.request()
    assert restarter.requested.is_set()
    assert closed == ["window"]
    assert signals == []


def test_a_setup_closes_the_program_without_a_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0031: the setup takes over; the boot must not start the old version again."""
    closed: list[str] = []
    signals: list[int] = []
    monkeypatch.setattr(signal, "raise_signal", signals.append)
    restarter = Restarter()
    restarter.close()
    restarter.use_window(lambda: closed.append("window"))
    restarter.close()
    assert not restarter.requested.is_set()
    assert (signals, closed) == ([signal.SIGINT], ["window"])


def test_without_a_window_a_restart_stops_the_server_like_ctrl_c(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[int] = []
    monkeypatch.setattr(signal, "raise_signal", signals.append)
    restarter = Restarter()
    restarter.request()
    assert signals == [signal.SIGINT]


def test_one_update_at_a_time(tmp_path: Path) -> None:
    started = threading.Event()
    go_on = threading.Event()

    def slow(request: httpx.Request) -> httpx.Response:
        started.set()
        go_on.wait(5)
        return github(PACKAGE)(request)

    restarts = Restarts()
    first = installer(tmp_path, slow, restarts)
    worker = threading.Thread(target=first.install, args=(release(),))
    worker.start()
    assert started.wait(5)
    with raises_exactly(ConflictError, "an update is being installed"):
        first.install(release())
    go_on.set()
    worker.join(5)
    assert restarts.done.wait(5)


def test_a_failed_download_lets_the_next_attempt_run(tmp_path: Path) -> None:
    answers = [httpx.Response(503), httpx.Response(200, content=PACKAGE)]

    def flaky(_request: httpx.Request) -> httpx.Response:
        return answers.pop(0)

    restarts = Restarts()
    attempt = installer(tmp_path, flaky, restarts)
    with pytest.raises(UnavailableError):
        attempt.install(release())
    attempt.install(release())
    assert restarts.done.wait(5)


def test_versions_taken_back_by_the_boot_count_as_failed(tmp_path: Path) -> None:
    save_state(tmp_path, State(active="0.6.2", failed=["0.7.0"]))
    taken_back = installer(tmp_path, github(PACKAGE), Restarts())
    assert taken_back.failed(release())
    assert taken_back.failed(replace(release(), candidate=2))  # by a boot before ADR 0035
    assert not taken_back.failed(replace(release(), version="0.7.1"))


def test_builds_taken_back_by_the_boot_count_as_failed(tmp_path: Path) -> None:
    """ADR 0035: the boot records the build; a later candidate of the version is not failed."""
    save_state(tmp_path, State(active="0.6.2", failed=["0.7.0-rc.2", "0.7.1"]))
    taken_back = PackageInstaller(tmp_path, "windows-x64", 1, Restarts(), builds=True)
    assert taken_back.failed(replace(release(), candidate=2))
    assert not taken_back.failed(replace(release(), candidate=3))
    assert not taken_back.failed(release())
    # A plain entry the boot could not resolve names no candidate's build.
    assert taken_back.failed(replace(release(), version="0.7.1"))
    assert not taken_back.failed(replace(release(), version="0.7.1", candidate=1))


def test_on_a_boot_that_knows_builds_each_candidate_gets_its_own_folder(tmp_path: Path) -> None:
    """ADR 0035: rc.3 beside the running rc.2 of the same version, for the boot to try."""
    client = httpx.Client(transport=httpx.MockTransport(github(MANIFEST_RC_2)))
    beta = PackageInstaller(
        tmp_path, "windows-x64", 1, Restarts(), client=client, restart_delay=0, builds=True,
        candidate=1,
    )  # fmt: skip
    assert beta.candidate == 1
    beta.install(replace(release(MANIFEST_RC_2), candidate=2))
    assert [path.name for path in (tmp_path / "app" / "versions").iterdir()] == ["0.7.0-rc.2"]


def test_on_an_earlier_boot_the_folder_is_named_after_the_version(tmp_path: Path) -> None:
    """Its boot orders the folders by their names, which must be versions it knows."""
    installer(tmp_path, github(MANIFEST_RC_2), Restarts()).install(
        replace(release(MANIFEST_RC_2), candidate=2)
    )
    assert [path.name for path in (tmp_path / "app" / "versions").iterdir()] == ["0.7.0"]


@pytest.mark.parametrize(
    ("build", "candidate"),
    [
        ("0.7.0-rc.3", 3),
        ("0.7.0-rc.12", 12),
        ("0.7.0", None),
        (None, None),
        ("0.7.1-rc.3", None),  # of another version
        ("0.7.00-rc.3", None),
        ("0.7.0-rc.0", None),
        ("0.7.0-rc.03", None),
        ("0.7.0-rc.", None),
        ("0.7.0-rc.3x", None),
        ("0.7.0-rc.\u0663", None),  # an Arabic-Indic three
    ],
)
def test_the_running_candidate_comes_from_the_boot(
    build: str | None, candidate: int | None
) -> None:
    assert running_candidate(build, "0.7.0") == candidate


def test_the_boot_and_the_package_name_the_build_alike() -> None:
    assert BUILD == rhinvoice_boot.BUILD
