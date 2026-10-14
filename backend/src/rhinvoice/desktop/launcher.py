"""``rhinvoice-desktop``: start Rhinvoice on this computer without Docker (ADR 0021).

On the first start it creates its configuration and database in the data folder.
Then it starts the database, opens the web interface in the browser once it answers,
and stops the database again when the program ends.

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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rhinvoice.api.cli import serve
from rhinvoice.api.settings import Settings
from rhinvoice.desktop.browser import find_chromium
from rhinvoice.desktop.config import ConfigError, load_or_create
from rhinvoice.desktop.folders import data_folder
from rhinvoice.desktop.ports import PortInUseError, free_port, require_free
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
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    desktop = Desktop(
        serve=serve,
        open_page=webbrowser.open,
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
        config = load_or_create(folder / "rhinvoice.json")
        require_free(config.port)
    except (ConfigError, PortInUseError, OSError) as error:
        return _failed(error)
    database = BundledPostgres(
        install / "postgresql" / "bin", folder / "database", config.database_password, free_port()
    )
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
        address = f"http://{HOST}:{config.port}"
        if not args.no_browser:
            threading.Thread(
                target=open_when_ready, args=(address, desktop.open_page), daemon=True
            ).start()
        sys.stdout.write(f"Rhinvoice runs on {address} (data: {folder})\n")
        return desktop.serve(settings, HOST, config.port)
    # ValueError: settings from RHINVOICE_* variables that are not valid.
    except (PostgresError, ValueError, OSError) as error:
        return _failed(error)
    finally:
        try:
            database.stop()
        except PostgresError as error:
            _failed(error)


def _failed(error: Exception) -> int:
    sys.stderr.write(f"error: {error}\n")
    return 1


def open_when_ready(
    address: str,
    open_page: Callable[[str], object],
    timeout: float = READY_TIMEOUT_SECONDS,
) -> bool:
    """Open the web interface once it answers; tell whether it did in time."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{address}/api/health", timeout=2):  # noqa: S310 - our own address
                open_page(address)
                return True
        except OSError:
            time.sleep(READY_POLL_SECONDS)
    return False
