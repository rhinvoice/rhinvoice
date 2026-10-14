"""Installing an update of the installation without Docker (ADR 0022)."""

import hashlib
import io
import json
import signal
import threading
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from rhinvoice.application.errors import UnavailableError
from rhinvoice.application.updates.ports import PackageFile, Release
from rhinvoice.desktop.updates import PackageInstaller, Restarter, platform_name

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
    (tmp_path / "app" / "versions" / "0.7.0").mkdir(parents=True)

    def nothing(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request)

    restarts = Restarts()
    installer(tmp_path, nothing, restarts).install(release())
    assert restarts.done.wait(5)


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


def test_without_a_window_a_restart_stops_the_server_like_ctrl_c(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[int] = []
    monkeypatch.setattr(signal, "raise_signal", signals.append)
    restarter = Restarter()
    restarter.request()
    assert signals == [signal.SIGINT]
