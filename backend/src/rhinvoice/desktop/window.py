"""The program window: the web interface in the system's own web view.

WebKit on macOS, Edge WebView2 on Windows (part of Windows 10 and 11), through pywebview,
which comes with the installers only (the ``desktop`` extra), not with the Docker image.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

TITLE = "Rhinvoice"
SIZE = (1280, 860)
MIN_SIZE = (960, 640)


def available() -> bool:
    """Tell whether windows can be shown (pywebview is installed)."""
    return importlib.util.find_spec("webview") is not None


def show(address: str, storage: Path) -> None:
    """Show the web interface in a window until it is closed.

    The window keeps its cookies in ``storage``: the login survives a restart.
    """
    import webview  # noqa: PLC0415 - only in the installers

    # Invoices, exports and backups are saved as files; links to other sites open in the browser.
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    # pywebview leaves the type of one of its parameters open (url: str | Unknown).
    webview.create_window(  # pyright: ignore[reportUnknownMemberType]
        TITLE, address, width=SIZE[0], height=SIZE[1], min_size=MIN_SIZE
    )
    webview.start(private_mode=False, storage_path=str(storage))
