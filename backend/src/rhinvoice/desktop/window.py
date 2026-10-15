"""The program window: the web interface in the system's own web view.

WebKit on macOS, Edge WebView2 on Windows (part of Windows 10 and 11), through pywebview,
which comes with the installers only (the ``desktop`` extra), not with the Docker image.

A start card shows right after the double click, while the database and the server
start; the program window replaces it once the interface has loaded. A second start
asks the running program to bring its window forward instead of opening another one.
"""

from __future__ import annotations

import contextlib
import html
import importlib.util
import json
import threading
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

TITLE = "Rhinvoice"
SIZE = (1280, 860)
MIN_SIZE = (960, 640)
CLOSE_DELAY_SECONDS = 0.05
SPLASH_SIZE = (520, 300)
SPLASH_BACKGROUND = "#1d4f80"
FORWARD_REQUEST = "show-request"
"""The file a second start leaves in the window folder: bring the window forward."""
FORWARD_POLL_SECONDS = 0.5
FAILED = 1
"""The exit code when the start ended without one (it failed before it could say)."""


class Card(Protocol):
    """The part of a pywebview window the program closes."""

    def destroy(self) -> None: ...


def available() -> bool:
    """Tell whether windows can be shown (pywebview is installed)."""
    return importlib.util.find_spec("webview") is not None


def close() -> None:
    """Close the program's windows: the program then ends (to restart after an update)."""
    import webview  # noqa: PLC0415 - only in the installers

    for shown in list(webview.windows):
        shown.destroy()


def run_with_splash(start: Callable[[Splash], int], storage: Path, version: str) -> int:
    """Show the start card, run ``start`` beside it and return its exit code.

    The windows need the main thread (macOS): ``start`` runs in a thread of its own, starts
    the database and the server and shows the program window (Splash.show) until it is
    closed. Whatever window is left when it ends is closed, which ends the window loop.
    The window keeps its cookies in ``storage``: the login survives a restart.
    """
    import webview  # noqa: PLC0415 - only in the installers

    # Invoices, exports and backups are saved as files; links to other sites open in the browser.
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    steps = StartSteps()
    card = webview.create_window(  # pyright: ignore[reportUnknownMemberType]
        TITLE,
        html=splash_html(version),
        js_api=steps,
        width=SPLASH_SIZE[0],
        height=SPLASH_SIZE[1],
        resizable=False,
        frameless=True,
        background_color=SPLASH_BACKGROUND,
        # pywebview types screens as its module_property; it reads as the list of screens.
        screen=main_screen(webview.screens),  # pyright: ignore[reportArgumentType]
    )
    splash = Splash(card, steps)
    if card is not None:
        # Quitting while it starts would end the process before the database stops.
        card.events.closing += splash.may_close
    codes: list[int] = []

    def body() -> None:
        try:
            codes.append(start(splash))
        finally:
            splash.close()
            close()

    # Not a daemon: after the window loop ends, the program still stops its database.
    worker = threading.Thread(target=body, name="rhinvoice")
    try:
        webview.start(worker.start, private_mode=False, storage_path=str(storage))
    finally:
        # Also when asked to end (Ctrl+C, Windows' CTRL_BREAK reach this thread only):
        # the start leaves its window and stops the server and the database first.
        splash.end()
        # Not started when the window loop could not start: then there is nothing to wait for.
        with contextlib.suppress(RuntimeError):
            worker.join()
    return codes[0] if codes else FAILED


class Placed(Protocol):
    """The part of a pywebview screen that tells where it is."""

    @property
    def x(self) -> int: ...

    @property
    def y(self) -> int: ...


def main_screen[S: Placed](screens: Sequence[S]) -> S | None:
    """Find the main screen, the one at the origin; None: let pywebview choose.

    Given a screen, pywebview centres the window on it. Without one, Windows places it
    at its default position near the top left: pywebview asks for the centre only once
    the window is being made, too late for Windows.
    """
    return next((screen for screen in screens if screen.x == 0 and screen.y == 0), None)


class StartSteps:
    """What the start card asks for, a few times a second (its js_api): the current step.

    Asked by the card, not told to it: telling would wait for the card's page, and the
    start must never wait for the card.
    """

    def __init__(self) -> None:
        self.steps = ["database"]

    def current(self) -> str:
        return self.steps[-1]


class Splash:
    """The start card: says what the start is doing, and gives way to the program window."""

    def __init__(self, card: Card | None, steps: StartSteps) -> None:
        self._card = card
        self._steps = steps
        self._done = threading.Event()
        self._ended = threading.Event()

    def status(self, step: str) -> None:
        """Show the step ("database", "data", "ready"); the card words it in its language."""
        self._steps.steps.append(step)

    def show(self, address: str, storage: Path) -> None:
        """Show the program window in place of the card until it is closed."""
        show(address, storage, loaded=self.close, ended=self._ended)

    def end(self) -> None:
        """Leave the program window as if it were closed (the program is asked to end)."""
        self._ended.set()

    def close(self) -> None:
        """Close the card once (the window has loaded, or the start ended)."""
        if self._done.is_set():
            return
        # Set first: closing asks may_close (on Windows also for the program's own close).
        self._done.set()
        if self._card is not None:
            self._card.destroy()

    def may_close(self) -> bool:
        """Let only the program close the card: quitting now would leave the database on."""
        return self._done.is_set()


def show(
    address: str,
    storage: Path,
    loaded: Callable[[], None] | None = None,
    ended: threading.Event | None = None,
) -> None:
    """Show the web interface in a program window until it is closed, or ``ended`` is set.

    Runs beside the window loop (run_with_splash). ``loaded`` is called once the interface
    has loaded; a request from a second start (``storage``/show-request) brings it forward.
    """
    import webview  # noqa: PLC0415 - only in the installers

    request = storage / FORWARD_REQUEST
    request.unlink(missing_ok=True)  # left by a start while none ran
    # pywebview leaves the type of one of its parameters open (url: str | Unknown).
    # Zoomable: pywebview otherwise listens to every wheel event to block Ctrl+wheel, and
    # WebKit then ignores scrolling on a page with overscroll-behavior (no rubber band,
    # index.css). Zooming also helps reading (WCAG 1.4.4).
    window = webview.create_window(  # pyright: ignore[reportUnknownMemberType]
        TITLE,
        address,
        width=SIZE[0],
        height=SIZE[1],
        min_size=MIN_SIZE,
        zoomable=True,
        # pywebview types screens as its module_property; it reads as the list of screens.
        screen=main_screen(webview.screens),  # pyright: ignore[reportArgumentType]
    )
    if window is None:
        return
    closed = ended or threading.Event()
    window.events.closing += close_cleanly(window.destroy)
    window.events.closed += closed.set
    if loaded is not None:
        window.events.loaded += loaded
    threading.Thread(target=forward_on_request, args=(window, request, closed), daemon=True).start()
    closed.wait()


class Raisable(Protocol):
    """The part of a pywebview window that brings it forward."""

    on_top: bool

    def restore(self) -> None: ...

    def show(self) -> None: ...


def forward_on_request(window: Raisable, request: Path, closed: threading.Event) -> None:
    """Bring the window forward whenever a second start asks, until it is closed."""
    while not closed.wait(FORWARD_POLL_SECONDS):
        if request.exists():
            request.unlink(missing_ok=True)
            bring_forward(window)


def bring_forward(window: Raisable) -> None:
    """Show the window in front of the others, also when it was minimized."""
    window.restore()
    window.show()
    # Raised above every window for a moment: Windows does not let a program take the
    # focus from another one otherwise.
    window.on_top = True
    window.on_top = False


def ask_to_bring_forward(storage: Path) -> None:
    """Ask the running program to bring its window forward (a second start)."""
    storage.mkdir(parents=True, exist_ok=True)
    (storage / FORWARD_REQUEST).touch()


def close_cleanly(destroy: Callable[[], None]) -> Callable[[], bool]:
    """Answer the question whether the window may close.

    The first time: no, but close it just after, the way the program expects. Quitting
    from the menu (Cmd+Q on macOS) would end the process right after this question,
    before the program stops its server and database; a closed window ends
    ``show`` instead, and the program cleans up as after any close. Our own
    close asks again (on Windows): then yes.
    """
    asked = threading.Event()

    def may_close() -> bool:
        if asked.is_set():
            return True
        asked.set()
        timer = threading.Timer(CLOSE_DELAY_SECONDS, destroy)
        timer.daemon = True
        timer.start()
        return False

    return may_close


SPLASH_TEXTS = {
    "de": {
        "database": "Datenbank wird gestartet …",
        "data": "Daten werden vorbereitet …",
        "ready": "Fast fertig …",
    },
    "en": {
        "database": "Starting the database …",
        "data": "Preparing the data …",
        "ready": "Almost ready …",
    },
}
"""The steps of a start in the card's languages; the web view knows the system's one."""

LOGO = (
    '<svg viewBox="0 0 32 32" aria-hidden="true"><defs><linearGradient id="g" x1="0" y1="0"'
    ' x2="1" y2="1"><stop offset="0" stop-color="#2a6db0"/><stop offset="1"'
    ' stop-color="#1d4f80"/></linearGradient></defs><rect width="32" height="32" rx="8"'
    ' fill="url(#g)"/><path d="M9 6.5h10l5 5v14a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 8'
    ' 25.5v-17.5A1.5 1.5 0 0 1 9.5 6.5Z" fill="#ffffff"/><path d="M19 6.5v5h5"'
    ' fill="#d6e6f6"/><path d="M11 9.8h4M11 12.4h5.5" stroke="#9db5cf" stroke-width="1.6"'
    ' stroke-linecap="round"/><g transform="translate(0 1.6)"><path d="M4.5 20C8 11 11 25'
    ' 16 16S24.5 9 27.5 13" fill="none" stroke="#6aa6d9" stroke-width="2.6"'
    ' stroke-linecap="round"/><circle cx="5.74" cy="17.67" r="2.3" fill="#ffffff"'
    ' stroke="#2a6db0" stroke-width="1.2"/><circle cx="11.97" cy="19.13" r="2.3"'
    ' fill="#ffffff" stroke="#2a6db0" stroke-width="1.2"/><circle cx="21.34" cy="9.9"'
    ' r="2.3" fill="#ffffff" stroke="#2a6db0" stroke-width="1.2"/><circle cx="27.05"'
    ' cy="12.42" r="2.3" fill="#ffffff" stroke="#2a6db0" stroke-width="1.2"/></g></svg>'
)
"""The logo of frontend/public/favicon.svg: the card loads nothing from elsewhere."""

SPLASH_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Rhinvoice</title><style>
html,body{margin:0;height:100%;overflow:hidden;cursor:default;user-select:none}
body{background:linear-gradient(135deg,#1d4f80,#123a62);color:#fff;
font:13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;display:flex;
flex-direction:column;justify-content:space-between;padding:28px 30px;box-sizing:border-box}
.top{display:flex;align-items:center;gap:16px}.top svg{width:64px;height:64px}
.name{font-size:30px;font-weight:700;letter-spacing:-.01em}.version{font-size:13px;opacity:.75}
.river{height:3px;border-radius:3px;background:rgb(255 255 255/.2);overflow:hidden;
margin-bottom:10px}
.river::after{content:"";display:block;height:100%;width:35%;background:#9cc8f0;
animation:flow 1.6s ease-in-out infinite}
@keyframes flow{from{transform:translateX(-100%)}to{transform:translateX(290%)}}
@media (prefers-reduced-motion:reduce){.river::after{animation:none;width:100%;opacity:.5}}
.bottom{display:flex;justify-content:space-between;gap:12px;opacity:.85;font-size:12px}
</style></head><body>
<div class="top">__LOGO__<div><div class="name">Rhinvoice</div>
<div class="version">Version __VERSION__ · Beta</div></div></div>
<div><div class="river"></div><div class="bottom"><span id="step" role="status"></span>
<span>by Webberz</span></div></div>
<script>
const texts = __TEXTS__;
const words = (navigator.language || "en").toLowerCase().startsWith("de") ? texts.de : texts.en;
function step(name) { document.getElementById("step").textContent = words[name] || ""; }
step("database");
window.addEventListener("pywebviewready", () => {
  const ask = () => window.pywebview.api.current().then(step, () => undefined);
  ask();
  setInterval(ask, 300);
});
</script></body></html>"""


def splash_html(version: str) -> str:
    """Write the start card's page: logo, name, version and the step of the start."""
    return (
        SPLASH_PAGE.replace("__LOGO__", LOGO)
        .replace("__VERSION__", html.escape(version))
        .replace("__TEXTS__", json.dumps(SPLASH_TEXTS, ensure_ascii=False))
    )
