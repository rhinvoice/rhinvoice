"""A headless Chromium on this computer, for installations without Gotenberg (ADR 0021).

Chrome, Edge and chrome-headless-shell all work. The browser is started on first use and
kept running; it is driven over the DevTools protocol on a port of 127.0.0.1 that it picks
itself. Printing uses the same page options as Gotenberg, so both give the same PDF.
"""

from __future__ import annotations

import atexit
import base64
import binascii
import json
import subprocess
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, cast

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from rhinvoice.application.errors import UnavailableError

if TYPE_CHECKING:
    from websockets.sync.client import ClientConnection

START_TIMEOUT_SECONDS = 15.0
STOP_TIMEOUT_SECONDS = 5.0
TIMEOUT_SECONDS = 30.0
POLL_SECONDS = 0.05
ARGUMENTS = (
    "--headless",
    "--remote-debugging-port=0",
    "--remote-allow-origins=",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--mute-audio",
)
# A4 in inches; the page has its own margins (see document.css). As for Gotenberg (pdf.py).
PRINT_OPTIONS: dict[str, object] = {
    "paperWidth": 8.27,
    "paperHeight": 11.69,
    "marginTop": 0,
    "marginBottom": 0,
    "marginLeft": 0,
    "marginRight": 0,
    "printBackground": True,
    "preferCSSPageSize": True,
    "generateTaggedPDF": True,
}
PAGE_FILE = "rhinvoice-page.html"
NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)
"""No console window for the browser on Windows (chrome-headless-shell is a console program)."""


class ProtocolError(Exception):
    """Chromium answered with an error or with something unexpected."""


class LocalChromiumPrinter:
    """The ``PagePrinter`` of installations without Docker (pdf.py)."""

    def __init__(
        self,
        binary: Path,
        *,
        start_timeout: float = START_TIMEOUT_SECONDS,
        timeout: float = TIMEOUT_SECONDS,
        stop_timeout: float = STOP_TIMEOUT_SECONDS,
    ) -> None:
        self._binary = binary
        self._start_timeout = start_timeout
        self._timeout = timeout
        self._stop_timeout = stop_timeout
        self._lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._profile: tempfile.TemporaryDirectory[str] | None = None
        self._endpoint = ""
        atexit.register(self.close)

    def print_pdf(self, page: str) -> bytes:
        """Print a complete HTML page (fonts and images inline) as a PDF."""
        with self._lock:
            endpoint, profile = self._running()
            try:
                content = self._print(endpoint, profile / PAGE_FILE, page)
            except (OSError, WebSocketException, ProtocolError) as error:
                # Started anew for the next page: the browser may have hung or crashed.
                self._stop()
                msg = "the PDF service (local Chromium) failed"
                raise UnavailableError(msg) from error
        if not content.startswith(b"%PDF-"):
            msg = "the PDF service (local Chromium) did not return a PDF"
            raise UnavailableError(msg)
        return content

    def close(self) -> None:
        with self._lock:
            self._stop()

    def _running(self) -> tuple[str, Path]:
        if self._process is not None and self._process.poll() is None and self._profile:
            return self._endpoint, Path(self._profile.name)
        self._stop()
        return self._start()

    def _start(self) -> tuple[str, Path]:
        # Helpers of the browser may still hold files when it ends (Windows refuses to delete them).
        profile = tempfile.TemporaryDirectory(
            prefix="rhinvoice-chromium-", ignore_cleanup_errors=True
        )
        folder = Path(profile.name)
        try:
            process = subprocess.Popen(  # noqa: S603 - the configured browser, fixed arguments
                [str(self._binary), *ARGUMENTS, f"--user-data-dir={folder}"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=NO_WINDOW,
            )
        except OSError as error:
            profile.cleanup()
            msg = f"the PDF service (local Chromium) cannot be started: {self._binary}"
            raise UnavailableError(msg) from error
        self._process, self._profile = process, profile
        deadline = time.monotonic() + self._start_timeout
        while process.poll() is None and time.monotonic() < deadline:
            # Chromium writes its port and the browser's path once it listens.
            lines = _lines(folder / "DevToolsActivePort")
            if len(lines) >= 2:  # noqa: PLR2004 - port and path
                self._endpoint = f"ws://127.0.0.1:{lines[0]}{lines[1]}"
                return self._endpoint, folder
            time.sleep(POLL_SECONDS)
        code = process.poll()
        self._stop()
        reason = "no answer" if code is None else f"exit code {code}"
        msg = f"the PDF service (local Chromium) did not start: {self._binary} ({reason})"
        raise UnavailableError(msg)

    def _stop(self) -> None:
        if self._process is not None:
            # Asked first, so that it ends its helper processes itself.
            self._process.terminate()
            try:
                self._process.wait(self._stop_timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None
        if self._profile is not None:
            self._profile.cleanup()
            self._profile = None

    def _print(self, endpoint: str, page_file: Path, page: str) -> bytes:
        page_file.write_text(page, encoding="utf-8")
        deadline = time.monotonic() + self._timeout
        with connect(endpoint, max_size=None, open_timeout=self._timeout) as socket:
            shared = _Shared()
            browser = _Session(socket, deadline, shared)
            target = _text(browser.call("Target.createTarget", {"url": "about:blank"}), "targetId")
            try:
                attached = browser.call(
                    "Target.attachToTarget", {"targetId": target, "flatten": True}
                )
                tab = _Session(socket, deadline, shared, _text(attached, "sessionId"))
                tab.call("Page.enable")
                # Only a load event after the navigation counts (not one of about:blank).
                since = shared.received()
                navigated = tab.call("Page.navigate", {"url": page_file.as_uri()})
                if "errorText" in navigated:
                    msg = f"the page did not load: {navigated['errorText']}"
                    raise ProtocolError(msg)
                tab.wait_for("Page.loadEventFired", since)
                # The fonts are inline, but decoding them may outlast the load event.
                tab.call(
                    "Runtime.evaluate", {"expression": "document.fonts.ready", "awaitPromise": True}
                )
                printed = tab.call("Page.printToPDF", PRINT_OPTIONS)
            finally:
                # A failure to close the tab must not hide why printing failed.
                with suppress(ProtocolError, WebSocketException, OSError):
                    browser.call("Target.closeTarget", {"targetId": target})
        try:
            return base64.b64decode(_text(printed, "data"), validate=True)
        except binascii.Error as error:
            msg = "the PDF is not base64"
            raise ProtocolError(msg) from error


class _Session:
    """Commands to the browser or to one tab; events that arrive meanwhile are kept."""

    def __init__(
        self,
        socket: ClientConnection,
        deadline: float,
        shared: _Shared,
        session_id: str | None = None,
    ) -> None:
        self._socket = socket
        self._deadline = deadline
        self._shared = shared
        self._session_id = session_id

    def call(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self._shared.last_id += 1
        command_id = self._shared.last_id
        message: dict[str, object] = {"id": command_id, "method": method, "params": params or {}}
        if self._session_id is not None:
            message["sessionId"] = self._session_id
        self._socket.send(json.dumps(message))
        while True:
            reply = self._receive()
            if reply.get("id") != command_id:
                self._shared.events.append(reply)
                continue
            if "error" in reply:
                msg = f"{method} failed: {reply['error']}"
                raise ProtocolError(msg)
            return _object(reply.get("result"))

    def wait_for(self, event: str, since: int) -> None:
        """Wait for an event of this session among the messages received after ``since``."""

        def wanted(message: dict[str, object]) -> bool:
            return message.get("method") == event and message.get("sessionId") == self._session_id

        while not any(wanted(message) for message in self._shared.events[since:]):
            self._shared.events.append(self._receive())

    def _receive(self) -> dict[str, object]:
        remaining = max(self._deadline - time.monotonic(), 0)
        try:
            message = self._socket.recv(timeout=remaining)
        except TimeoutError as error:
            msg = "Chromium took too long"
            raise ProtocolError(msg) from error
        try:
            return _object(json.loads(message))
        except ValueError as error:
            msg = "Chromium sent no JSON"
            raise ProtocolError(msg) from error


class _Shared:
    """The state that the browser's and the tab's session share on one connection."""

    def __init__(self) -> None:
        self.last_id = 0
        self.events: list[dict[str, object]] = []

    def received(self) -> int:
        """Count the events received so far."""
        return len(self.events)


def _lines(path: Path) -> list[str]:
    """Read the port file; not there yet or still being written means: not ready yet."""
    try:
        return path.read_text(encoding="utf-8").split()
    except OSError:
        # Windows refuses to open a file while the browser writes it (sharing violation).
        return []


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"expected an object, got {value!r:.80}"
        raise ProtocolError(msg)
    # Keys of JSON objects are always text.
    return cast("dict[str, object]", value)


def _text(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        msg = f"expected text in {key!r}"
        raise ProtocolError(msg)
    return item
