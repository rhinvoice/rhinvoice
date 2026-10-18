"""Install an update of the installation without Docker: the release's app package (ADR 0022).

The package is downloaded with the size and SHA-256 of the signed release.json, unpacked
next to the others as ``<version>.partial`` and renamed when complete. Then the program
restarts; the boot copies the database and lets the new version prove itself.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import signal
import tempfile
import threading
import zipfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import httpx

from rhinvoice.application.errors import ConflictError, UnavailableError
from rhinvoice_boot import load_state

if TYPE_CHECKING:
    from collections.abc import Callable

    from rhinvoice.application.updates.ports import PackageFile, Release

TIMEOUT_SECONDS = 60.0
CHUNK_BYTES = 1024 * 1024
RESTART_DELAY_SECONDS = 1.0
"""Long enough for the answer to the request to reach the browser."""


def platform_name(system: str, machine: str) -> str:
    """Name the platform as release.json does, e.g. "windows-x64" or "macos-arm64"."""
    os_name = {"Windows": "windows", "Darwin": "macos"}.get(system, system.lower())
    arch = "arm64" if machine.lower() in {"arm64", "aarch64"} else "x64"
    return f"{os_name}-{arch}"


class Restarter:
    """Ends the program so that the boot starts it again (exit code RESTART)."""

    def __init__(self) -> None:
        self.requested = threading.Event()
        self._close_window: Callable[[], None] | None = None

    def use_window(self, close: Callable[[], None]) -> None:
        """End the program by closing its window while it shows one."""
        self._close_window = close

    def request(self) -> None:
        self.requested.set()
        if self._close_window is not None:
            self._close_window()
        else:
            # The server runs in the main thread: stop it as Ctrl+C would.
            signal.raise_signal(signal.SIGINT)


class PackageInstaller:
    """The ``UpdateInstaller`` port of the installation without Docker."""

    def __init__(  # noqa: PLR0913 - the surroundings of an update
        self,
        data: Path,
        platform: str,
        runtime: int,
        restart: Callable[[], None],
        *,
        client: httpx.Client | None = None,
        restart_delay: float = RESTART_DELAY_SECONDS,
        setup: str | None = None,
    ) -> None:
        self.platform = platform
        self.setup = setup or platform
        self.runtime = runtime
        self._versions = data / "app" / "versions"
        self._restart = restart
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True)
        self._restart_delay = restart_delay
        self._data = data
        self._installing = threading.Lock()

    def install(self, release: Release) -> None:
        # One at a time: a second request would share the .partial folder.
        if not self._installing.acquire(blocking=False):
            raise ConflictError("an update is being installed", code="update_running")
        try:
            target = self._versions / release.version
            if not target.is_dir():
                self._put_in_place(release, release.packages[self.platform], target)
        except BaseException:
            self._installing.release()
            raise
        # Held until the program ends: the restart follows.
        timer = threading.Timer(self._restart_delay, self._restart)
        timer.daemon = True
        timer.start()

    def failed(self, version: str) -> bool:
        return version in load_state(self._data).failed

    def _put_in_place(self, release: Release, package: PackageFile, target: Path) -> None:
        partial = target.with_name(target.name + ".partial")
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir(parents=True)
        try:
            with tempfile.TemporaryDirectory() as folder:
                archive = Path(folder) / "package.zip"
                self._download(package, archive)
                unpack(archive, partial)
            check_manifest(partial, release)
            partial.rename(target)
        except Exception:
            shutil.rmtree(partial, ignore_errors=True)
            raise

    def _download(self, package: PackageFile, archive: Path) -> None:
        digest = hashlib.sha256()
        size = 0
        try:
            with self._client.stream("GET", package.url) as response, archive.open("wb") as file:
                response.raise_for_status()
                for chunk in response.iter_bytes(CHUNK_BYTES):
                    size += len(chunk)
                    if size > package.size:
                        break
                    digest.update(chunk)
                    file.write(chunk)
        except httpx.HTTPError as error:
            msg = f"the update could not be downloaded: {error}"
            raise UnavailableError(msg) from error
        if size != package.size or digest.hexdigest() != package.sha256:
            msg = "the downloaded update is not the released one"
            raise UnavailableError(msg)


def unpack(archive: Path, target: Path) -> None:
    """Unpack the package, refusing paths that would leave ``target``."""
    with zipfile.ZipFile(archive) as zipped:
        for name in zipped.namelist():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or ":" in name:
                msg = f"the update contains an unsafe path: {name}"
                raise UnavailableError(msg)
        # Every path was checked above.
        zipped.extractall(target)


def check_manifest(package: Path, release: Release) -> None:
    try:
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        matches = manifest["version"] == release.version and manifest["runtime"] == release.runtime
    except (OSError, ValueError, KeyError, TypeError) as error:
        msg = "the update has no valid manifest.json"
        raise UnavailableError(msg) from error
    if not matches:
        msg = "the update's manifest.json does not match the release"
        raise UnavailableError(msg)
