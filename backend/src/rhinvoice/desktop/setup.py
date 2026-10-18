"""Install a new setup from within the program (ADR 0031).

A release whose app package needs a newer runtime needs its setup (ADR 0022). The program
downloads it with the size and SHA-256 of the signed release.json, in the background so
that the page can show the progress, into ``<data>/app/setup/<version>/``. Once the user
agrees, it starts a helper and closes itself; the helper waits until the program has ended
and installs:

- Windows: the setup itself, quietly (``/SILENT``). Started with ``/FROMRHINVOICE``, it waits
  until no Rhinvoice of its edition runs (the mutex ``Edition.mutex``) and starts it again.
- macOS: a shell script that waits for the session lock of the boot, replaces the app in
  place from the disk image and opens it; if anything goes wrong it shows the disk image,
  so that the app can be dragged into the Applications folder by hand.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import replace
from typing import TYPE_CHECKING

import httpx

from rhinvoice.application.errors import ConflictError
from rhinvoice.application.updates.handlers import is_newer
from rhinvoice.application.updates.ports import SetupProgress, SetupState

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from rhinvoice.application.updates.ports import PackageFile

TIMEOUT_SECONDS = 60.0
CHUNK_BYTES = 1024 * 1024
CLOSE_DELAY_SECONDS = 1.0
"""Long enough for the answer to the request to reach the page."""
FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.(exe|dmg)")

DETACHED: int = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
    subprocess, "CREATE_NEW_PROCESS_GROUP", 0
)
"""On Windows: the setup outlives the program and gets no console."""

WINDOWS_ARGUMENTS = ("/SILENT", "/SP-", "/NORESTART", "/FROMRHINVOICE")
"""Quiet, but with its progress and any question; /FROMRHINVOICE: wait for the program,
then start it again (desktop/windows/rhinvoice.iss)."""

MACOS_SCRIPT = r"""
lock="$1" image="$2" bundle="$3"
show_image() { /usr/bin/open "$image"; exit 0; }
# The program has ended once its boot's session lock is free (rhinvoice_boot.session).
/usr/bin/lockf -k -t 600 "$lock" /usr/bin/true || show_image
case "$bundle" in *.app) ;; *) show_image ;; esac
mount="$(/usr/bin/mktemp -d)" || show_image
/usr/bin/hdiutil attach -nobrowse -noautoopen -readonly -mountpoint "$mount" "$image" \
    >/dev/null || show_image
name="$(/usr/bin/basename "$bundle")"
/bin/rm -rf "$bundle.new" "$bundle.old"
if /usr/bin/ditto "$mount/$name" "$bundle.new" && /bin/mv "$bundle" "$bundle.old"; then
    if /bin/mv "$bundle.new" "$bundle"; then
        /bin/rm -rf "$bundle.old"
        /usr/bin/hdiutil detach -quiet "$mount"
        /usr/bin/open "$bundle"
        exit 0
    fi
    /bin/mv "$bundle.old" "$bundle"
fi
/bin/rm -rf "$bundle.new"
/usr/bin/hdiutil detach -quiet "$mount"
show_image
"""
"""Run by /bin/sh after the program has closed: replace the app, or show the disk image."""


def helper_command(setup: Path, *, system: str, data: Path, install: Path) -> list[str]:
    """Return what installs ``setup`` once the program has ended."""
    if system == "Windows":
        return [str(setup), *WINDOWS_ARGUMENTS]
    # The runtime lies in Rhinvoice.app/Contents/Resources (desktop/build.py).
    bundle = install.parent.parent
    lock = data / "app" / "session.lock"
    return ["/bin/sh", "-c", MACOS_SCRIPT, "rhinvoice-setup", str(lock), str(setup), str(bundle)]


def start_detached(command: Sequence[str]) -> None:
    """Start ``command`` so that it outlives this program."""
    subprocess.Popen(  # noqa: S603 - our own setup, or /bin/sh with our script
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=DETACHED,
        start_new_session=True,
        close_fds=True,
    )


def mark_running(name: str) -> int | None:
    """Hold a named mutex while this program runs, on Windows; its setup waits for it.

    The handle is never closed: the system releases the mutex when the process ends.
    """
    if sys.platform == "win32":  # pragma: no cover - the CI smoke test runs this on Windows
        import ctypes  # noqa: PLC0415

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        not_owned = 0
        return int(kernel32.CreateMutexW(None, not_owned, name))
    return None


class SetupDownloader:
    """The ``SetupInstaller`` port of the installation without Docker."""

    def __init__(  # noqa: PLR0913 - the surroundings of a setup
        self,
        data: Path,
        current: str,
        command: Callable[[Path], list[str]],
        close: Callable[[], None],
        *,
        client: httpx.Client | None = None,
        start: Callable[[Sequence[str]], None] = start_detached,
        close_delay: float = CLOSE_DELAY_SECONDS,
    ) -> None:
        """``command`` installs a downloaded setup; ``close`` ends the program."""
        self._folder = data / "app" / "setup"
        self._command = command
        self._close = close
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True)
        self._start = start
        self._close_delay = close_delay
        self._lock = threading.Lock()
        self._progress = SetupProgress()
        self._file: Path | None = None
        self._forget_installed(current)

    def download(self, version: str, setup: PackageFile) -> None:
        with self._lock:
            if self._progress.version == version and self._progress.state in {
                SetupState.DOWNLOADING,
                SetupState.READY,
            }:
                return
            self._progress = SetupProgress(SetupState.DOWNLOADING, version, 0, setup.size)
        worker = threading.Thread(target=self._fetch, args=(version, setup), daemon=True)
        worker.start()

    def progress(self) -> SetupProgress:
        with self._lock:
            return self._progress

    def run(self) -> None:
        with self._lock:
            setup = self._file
            if self._progress.state is not SetupState.READY or setup is None:
                raise ConflictError("the setup is not downloaded yet", code="setup_not_ready")
        self._start(self._command(setup))
        timer = threading.Timer(self._close_delay, self._close)
        timer.daemon = True
        timer.start()

    def _fetch(self, version: str, setup: PackageFile) -> None:
        try:
            path = self._save(version, setup)
        except (httpx.HTTPError, OSError, ValueError):
            with self._lock:
                self._progress = replace(self._progress, state=SetupState.FAILED)
            return
        with self._lock:
            self._file = path
            self._progress = replace(self._progress, state=SetupState.READY)

    def _save(self, version: str, setup: PackageFile) -> Path:
        name = setup.url.rsplit("/", 1)[-1]
        if not FILE_NAME.fullmatch(name):
            msg = f"'{name}' is not the name of a setup"
            raise ValueError(msg)
        # Only one setup at a time: an older download is of no use any more.
        shutil.rmtree(self._folder, ignore_errors=True)
        folder = self._folder / version
        folder.mkdir(parents=True)
        partial = folder / (name + ".partial")
        try:
            received, digest = self._fetch_into(setup, partial)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        if received != setup.size or digest != setup.sha256:
            partial.unlink()
            msg = "the downloaded setup is not the released one"
            raise ValueError(msg)
        return partial.rename(folder / name)

    def _fetch_into(self, setup: PackageFile, partial: Path) -> tuple[int, str]:
        """Download into ``partial``; return the size and SHA-256 of what came."""
        digest = hashlib.sha256()
        received = 0
        with self._client.stream("GET", setup.url) as response, partial.open("wb") as file:
            response.raise_for_status()
            for chunk in response.iter_bytes(CHUNK_BYTES):
                received += len(chunk)
                if received > setup.size:
                    break
                digest.update(chunk)
                file.write(chunk)
                with self._lock:
                    self._progress = replace(self._progress, received=received)
        return received, digest.hexdigest()

    def _forget_installed(self, current: str) -> None:
        """Remove a setup that is installed by now (it keeps tens of megabytes)."""
        if not self._folder.is_dir():
            return
        for folder in self._folder.iterdir():
            if not is_newer(folder.name, current):
                shutil.rmtree(folder, ignore_errors=True)
