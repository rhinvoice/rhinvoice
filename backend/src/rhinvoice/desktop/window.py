"""The program window: the web interface in the system's own web view.

WebKit on macOS, Edge WebView2 on Windows (part of Windows 10 and 11), through pywebview,
which comes with the installers only (the ``desktop`` extra), not with the Docker image.
"""

from __future__ import annotations

import importlib.util
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

TITLE = "Rhinvoice"
SIZE = (1280, 860)
MIN_SIZE = (960, 640)
CLOSE_DELAY_SECONDS = 0.05


def available() -> bool:
    """Tell whether windows can be shown (pywebview is installed)."""
    return importlib.util.find_spec("webview") is not None


def close() -> None:
    """Close the program's windows: the program then ends (to restart after an update)."""
    import webview  # noqa: PLC0415 - only in the installers

    for shown in list(webview.windows):
        shown.destroy()


def show(address: str, storage: Path) -> None:
    """Show the web interface in a window until it is closed.

    The window keeps its cookies in ``storage``: the login survives a restart.
    """
    import webview  # noqa: PLC0415 - only in the installers

    # Invoices, exports and backups are saved as files; links to other sites open in the browser.
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    # pywebview leaves the type of one of its parameters open (url: str | Unknown).
    # Zoomable: pywebview otherwise listens to every wheel event to block Ctrl+wheel, and
    # WebKit then ignores scrolling on a page with overscroll-behavior (no rubber band,
    # index.css). Zooming also helps reading (WCAG 1.4.4).
    window = webview.create_window(  # pyright: ignore[reportUnknownMemberType]
        TITLE, address, width=SIZE[0], height=SIZE[1], min_size=MIN_SIZE, zoomable=True
    )
    if window is not None:
        window.events.closing += close_cleanly(window.destroy)
    webview.start(private_mode=False, storage_path=str(storage))


def close_cleanly(destroy: Callable[[], None]) -> Callable[[], bool]:
    """Answer the question whether the window may close.

    The first time: no, but close it just after, the way the program expects. Quitting
    from the menu (Cmd+Q on macOS) would end the process right after this question,
    before the program stops its server and database; a closed window ends
    ``webview.start`` instead, and the program cleans up as after any close. Our own
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
