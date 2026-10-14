"""``rhinvoice-desktop``: start Rhinvoice on this computer without Docker (ADR 0021).

On the first start it creates its configuration and database in the data folder.
Then it starts the database and shows the web interface in a program window once it
answers (in the browser where windows are not available, or with ``--browser``), and
stops the database again when the window is closed.

The installer lays out its folder as ``python/`` (this interpreter), ``postgresql/``,
``static/`` (the web interface) and optionally ``chromium/``.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from rhinvoice.api.cli import serve
from rhinvoice.api.settings import Settings
from rhinvoice.desktop import window
from rhinvoice.desktop.browser import find_chromium
from rhinvoice.desktop.config import ConfigError, DesktopConfig, load_or_create, save
from rhinvoice.desktop.folders import data_folder
from rhinvoice.desktop.ports import free_port, listening
from rhinvoice.desktop.postgres import BundledPostgres, PostgresError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

HOST = "127.0.0.1"
READY_TIMEOUT_SECONDS = 60.0
READY_POLL_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class Desktop:
    """What the program needs from its surroundings; tests replace these."""

    serve: Callable[[Settings, str, int], int]
    open_page: Callable[[str], object]
    show_window: Callable[[str, Path], None] | None
    """Shows the address in a program window until it is closed; None without windows."""
    system: str
    environ: dict[str, str]
    home: Path
    install: Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rhinvoice-desktop", description="Start Rhinvoice on this computer."
    )
    parser.add_argument("--data-dir", type=Path, help="where the database and settings live")
    parser.add_argument("--install-dir", type=Path, help="the installed program's folder")
    parser.add_argument("--browser", action="store_true", help="use the browser, not a window")
    parser.add_argument(
        "--no-browser", action="store_true", help="open neither window nor browser (a server)"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    desktop = Desktop(
        serve=serve,
        open_page=webbrowser.open,
        show_window=window.show if window.available() else None,
        system=platform.system(),
        environ=dict(os.environ),
        home=Path.home(),
        # The bundled interpreter lives in <install>/python.
        install=Path(sys.prefix).parent,
    )
    return run(build_parser().parse_args(argv), desktop)


def run(args: argparse.Namespace, desktop: Desktop) -> int:
    install: Path = args.install_dir or desktop.install
    folder: Path = args.data_dir or data_folder(desktop.system, desktop.environ, desktop.home)
    try:
        _log_without_console(folder)
        config = load_or_create(folder / "rhinvoice.json")
        database = BundledPostgres(
            install / "postgresql" / "bin",
            folder / "database",
            config.database_password,
            free_port(),
        )
        if _already_running(database, config.port):
            # Started a second time (a double click too many): show the running one.
            sys.stdout.write(f"Rhinvoice runs already on {_address(config.port)}\n")
            _show(args, desktop, _address(config.port), folder)
            return 0
        config = _own_port(config, folder)
    except (ConfigError, PostgresError, OSError) as error:
        return _failed(error)
    try:
        database.start()
        settings = Settings(
            database_url=database.url,
            chromium_path=find_chromium(desktop.system, desktop.environ, install),
            static_dir=install / "static",
            # Only this computer reaches the server, over http; Safari refuses secure
            # cookies there.
            cookie_secure=False,
        )
        return _serve(args, desktop, settings, config.port, folder)
    # ValueError: settings from RHINVOICE_* variables that are not valid.
    except (PostgresError, ValueError, OSError) as error:
        return _failed(error)
    finally:
        try:
            database.stop()
        except PostgresError as error:
            _failed(error)


def _own_port(config: DesktopConfig, folder: Path) -> DesktopConfig:
    """Keep the configured port, or take a free one when another program has it."""
    if not listening(config.port):
        return config
    # Kept for the next starts: bookmarks stay valid from then on.
    moved = replace(config, port=free_port())
    save(folder / "rhinvoice.json", moved)
    return moved


def _serve(
    args: argparse.Namespace, desktop: Desktop, settings: Settings, port: int, folder: Path
) -> int:
    address = _address(port)
    sys.stdout.write(f"Rhinvoice runs on {address} (data: {folder})\n")
    if args.no_browser or args.browser or desktop.show_window is None:
        if not args.no_browser:
            threading.Thread(
                target=open_when_ready, args=(address, desktop.open_page), daemon=True
            ).start()
        return desktop.serve(settings, HOST, port)
    # The window needs the main thread (macOS); the server runs beside it and ends with
    # the program when the window is closed.
    threading.Thread(target=desktop.serve, args=(settings, HOST, port), daemon=True).start()
    if not wait_until_answers(address):
        msg = f"the web interface did not start on {address}"
        raise TimeoutError(msg)
    _show(args, desktop, address, folder)
    return 0


def _show(args: argparse.Namespace, desktop: Desktop, address: str, folder: Path) -> None:
    if args.no_browser:
        return
    if args.browser or desktop.show_window is None:
        desktop.open_page(address)
    else:
        desktop.show_window(address, folder / "window")


def _log_without_console(folder: Path) -> None:
    """Write the messages to a file when there is no console (pythonw.exe, an app bundle)."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    log = (folder / "rhinvoice.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def _already_running(database: BundledPostgres, port: int) -> bool:
    # Its own database runs and its port answers. A database left over from a killed
    # program has no web interface: then it is restarted (BundledPostgres.start).
    return database.running() and answers(_address(port))


def _address(port: int) -> str:
    return f"http://{HOST}:{port}"


def answers(address: str) -> bool:
    """Tell whether the web interface at this address answers."""
    try:
        with urllib.request.urlopen(f"{address}/api/health", timeout=2):  # noqa: S310 - our own address
            return True
    except OSError:
        return False


def _failed(error: Exception) -> int:
    sys.stderr.write(f"error: {error}\n")
    return 1


def open_when_ready(
    address: str,
    open_page: Callable[[str], object],
    timeout: float = READY_TIMEOUT_SECONDS,
) -> bool:
    """Open the web interface once it answers; tell whether it did in time."""
    if not wait_until_answers(address, timeout):
        return False
    open_page(address)
    return True


def wait_until_answers(address: str, timeout: float = READY_TIMEOUT_SECONDS) -> bool:
    """Wait for the web interface; tell whether it answered in time."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if answers(address):
            return True
        time.sleep(READY_POLL_SECONDS)
    return False
