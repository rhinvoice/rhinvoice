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
import getpass
import os
import platform
import signal
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from rhinvoice.api.cli import serve
from rhinvoice.api.container import NO_OWN_SERVICES, OwnServices
from rhinvoice.api.settings import Settings
from rhinvoice.application.backup.ports import BackupFailed
from rhinvoice.desktop import window
from rhinvoice.desktop.backup import CurrentArchive, DesktopBackupSetup, cloud_folders
from rhinvoice.desktop.browser import find_chromium
from rhinvoice.desktop.config import ConfigError, DesktopConfig, load_or_create, save, update
from rhinvoice.desktop.ports import free_port, listening
from rhinvoice.desktop.postgres import BundledPostgres, PostgresError
from rhinvoice.desktop.updates import PackageInstaller, Restarter, platform_name
from rhinvoice.infrastructure.backup.restic import ResticArchive
from rhinvoice_boot import (
    RESTART,
    BootError,
    confirm,
    data_folder,
    log_without_console,
    runtime_generation,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from rhinvoice.application.backup.ports import FolderSuggestion


HOST = "127.0.0.1"
ATTACH_SECONDS = 600.0
"""How long a second start waits for the first one (which may migrate a large database)."""
SERVER_STOP_SECONDS = 30.0
READY_POLL_SECONDS = 0.25
RESTIC = ("restic.exe", "restic")


class Server(Protocol):
    def __call__(
        self,
        settings: Settings,
        host: str,
        port: int,
        *,
        own: OwnServices = NO_OWN_SERVICES,
        stop: threading.Event | None = None,
    ) -> int:
        """Run the web server until it is stopped, or until ``stop`` is set (api.cli.serve)."""
        ...


@dataclass(frozen=True, slots=True)
class Desktop:
    """What the program needs from its surroundings; tests replace these."""

    serve: Server
    open_page: Callable[[str], object]
    show_window: Callable[[str, Path], None] | None
    """Shows the address in a program window until it is closed; None without windows."""
    system: str
    machine: str
    """platform.machine(): the processor, for the update package (x64 or arm64)."""
    environ: dict[str, str]
    home: Path
    install: Path
    close_window: Callable[[], None] | None = None
    """Closes the window that show_window shows (for a restart after an update)."""
    ask_secret: Callable[[str], str] = getpass.getpass
    """Asks for the recovery key of a restore, without showing it."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rhinvoice-desktop", description="Start Rhinvoice on this computer."
    )
    parser.add_argument("--data-dir", type=Path, help="where the database and settings live")
    parser.add_argument("--install-dir", type=Path, help="the installed program's folder")
    parser.add_argument(
        "--static-dir", type=Path, help="the web interface (default: static in the install folder)"
    )
    parser.add_argument("--browser", action="store_true", help="use the browser, not a window")
    parser.add_argument(
        "--no-browser", action="store_true", help="open neither window nor browser (a server)"
    )
    parser.add_argument(
        "--attach", action="store_true", help="only show the program that already runs (the boot)"
    )
    parser.add_argument(
        "--restore",
        metavar="BACKUP",
        help='replace the data with a backup ("latest" or its ID), then end; quit Rhinvoice first',
    )
    parser.add_argument("--list-backups", action="store_true", help="list the backups, then end")
    parser.add_argument(
        "--backup-folder",
        type=Path,
        help="the folder of the backups (to restore on a new computer)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    desktop = Desktop(
        serve=serve,
        open_page=webbrowser.open,
        show_window=window.show if window.available() else None,
        close_window=window.close if window.available() else None,
        system=platform.system(),
        machine=platform.machine(),
        environ=dict(os.environ),
        home=Path.home(),
        # The bundled interpreter lives in <install>/python.
        install=Path(sys.prefix).parent,
    )
    end_on_break()
    try:
        return run(build_parser().parse_args(argv), desktop)
    except KeyboardInterrupt:
        # Asked to end (Ctrl+C, or Windows): the server and the database are stopped by now.
        return 0


def end_on_break() -> None:
    """Treat Windows' request to end (CTRL_BREAK: logging off, a task manager) as Ctrl+C.

    uvicorn stops the server on it and then raises the signal again; without a handler
    Windows ends the process at once, before the program stops its database. As
    KeyboardInterrupt it passes through every cleanup on its way out.
    """
    sigbreak = getattr(signal, "SIGBREAK", None)
    if sigbreak is not None:
        signal.signal(sigbreak, signal.default_int_handler)


def run(args: argparse.Namespace, desktop: Desktop) -> int:
    install: Path = args.install_dir or desktop.install
    folder: Path = args.data_dir or data_folder(desktop.system, desktop.environ, desktop.home)
    if args.restore is not None or args.list_backups:
        return _restore(args, desktop, install, folder)
    if args.attach:
        return _attach(args, desktop, folder)
    try:
        log_without_console(folder)
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
            static_dir=args.static_dir or install / "static",
            # Only this computer reaches the server, over http; Safari refuses secure
            # cookies there.
            cookie_secure=False,
        )
        restarter = Restarter()
        own = _own_services(desktop, install, folder, database.url, restarter)
        code = _serve(args, desktop, settings, config.port, folder, own=own, restarter=restarter)
        # After an update the boot starts the program again, with the new version.
        return RESTART if restarter.requested.is_set() else code
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


def _own_services(
    desktop: Desktop, install: Path, folder: Path, database_url: str, restarter: Restarter
) -> OwnServices:
    """Bring updates and backups, when the installed program has what they need."""
    setup, archive = _backups(desktop, install, folder, database_url)
    return OwnServices(
        installer=_installer(desktop, install, folder, restarter),
        backup_setup=setup,
        backup_archive=archive,
    )


def _backups(
    desktop: Desktop, install: Path, folder: Path, database_url: str
) -> tuple[DesktopBackupSetup, CurrentArchive] | tuple[None, None]:
    """Back up with the bundled restic (ADR 0023); without it (a source tree) there is none."""
    restic = _restic(install)
    if restic is None:
        return None, None
    pg_dump = install / "postgresql" / "bin" / "pg_dump"
    config = folder / "rhinvoice.json"

    def archive_for(target: Path, key: str) -> ResticArchive:
        return ResticArchive(restic, pg_dump, target, key, database_url)

    def suggestions() -> list[FolderSuggestion]:
        return cloud_folders(desktop.system, desktop.environ, desktop.home)

    archive = CurrentArchive(config, archive_for, lambda: datetime.now(UTC))
    return DesktopBackupSetup(config, archive_for, suggestions), archive


def _restic(install: Path) -> Path | None:
    """Find the bundled restic (restic.exe on Windows)."""
    return next(
        (path for path in (install / "restic" / name for name in RESTIC) if path.is_file()), None
    )


def _restore(args: argparse.Namespace, desktop: Desktop, install: Path, folder: Path) -> int:
    """Replace the data with a backup, or list the backups (ADR 0023); then end."""
    try:
        _restore_or_list(args, desktop, install, folder)
    except (BackupFailed, ConfigError, PostgresError, OSError) as error:
        return _failed(error)
    return 0


def _restore_or_list(
    args: argparse.Namespace, desktop: Desktop, install: Path, folder: Path
) -> None:
    restic = _restic(install)
    if restic is None:
        msg = "this installation has no restic to restore with"
        raise BackupFailed(msg)
    config = load_or_create(folder / "rhinvoice.json")
    binaries = install / "postgresql" / "bin"
    database = BundledPostgres(binaries, folder / "database", config.database_password, free_port())
    # The boot adds --attach when the program runs already.
    if args.attach or _already_running(database, config.port):
        msg = "Rhinvoice runs: quit it first"
        raise BackupFailed(msg)
    backups = _backup_folder(args.backup_folder) or config.backup_folder
    if backups is None:
        msg = "name the folder of the backups: --backup-folder <folder>"
        raise BackupFailed(msg)
    # The key of the folder set up here, else the one the person kept.
    known = config.backup_key if str(backups) == config.backup_folder else None
    key = known or desktop.ask_secret("Recovery key: ").strip()
    archive = ResticArchive(restic, binaries / "pg_dump", Path(backups), key, database.url)
    if args.restore is None:
        sys.stdout.write(archive.snapshots())
        return
    database.start()
    try:
        archive.restore(args.restore, binaries / "psql")
    finally:
        database.stop()
    # Backups go on into the same folder, with the key that opened it.
    update(
        folder / "rhinvoice.json",
        lambda kept: replace(
            kept, backup_folder=str(backups), backup_key=key, backup_key_confirmed=True
        ),
    )
    sys.stdout.write(f"Restored {args.restore} from {backups}; start Rhinvoice again.\n")


def _backup_folder(given: Path | None) -> str | None:
    """Keep a named backup folder as a full path: backups go on into it after the restore."""
    if given is None:
        return None
    folder = given.expanduser()
    if not folder.is_absolute():
        msg = "give the full path of the backup folder"
        raise BackupFailed(msg)
    return str(folder.resolve())


def _installer(
    desktop: Desktop, install: Path, folder: Path, restarter: Restarter
) -> PackageInstaller | None:
    """Install updates when started by the boot of an installed runtime (ADR 0022)."""
    try:
        runtime = runtime_generation(install)
    except BootError:
        # Started from a source tree or a virtual environment: nothing to install into.
        return None
    platform = platform_name(desktop.system, desktop.machine)
    return PackageInstaller(folder, platform, runtime, restarter.request)


def _serve(  # noqa: PLR0913 - the parts of one start (keywords for the update's)
    args: argparse.Namespace,
    desktop: Desktop,
    settings: Settings,
    port: int,
    folder: Path,
    *,
    own: OwnServices,
    restarter: Restarter,
) -> int:
    address = _address(port)
    sys.stdout.write(f"Rhinvoice runs on {address} (data: {folder})\n")
    if args.no_browser or args.browser or desktop.show_window is None:
        open_page = None if args.no_browser else desktop.open_page
        threading.Thread(target=when_ready, args=(address, folder, open_page), daemon=True).start()
        return desktop.serve(settings, HOST, port, own=own)
    # The window needs the main thread (macOS); the server runs beside it. Closing the
    # window stops the server and its background jobs before the database stops.
    if desktop.close_window is not None:
        restarter.use_window(desktop.close_window)
    stop = threading.Event()
    server = threading.Thread(
        target=desktop.serve,
        args=(settings, HOST, port),
        kwargs={"own": own, "stop": stop},
        daemon=True,
    )
    server.start()
    try:
        # No time limit: a first start may migrate for a while, and a version that works
        # must never be taken for a failed one.
        if not when_ready(address, folder, running=server.is_alive):
            msg = f"the web interface did not start on {address}"
            raise OSError(msg)
        _show(args, desktop, address, folder)
    finally:
        stop.set()
        server.join(SERVER_STOP_SECONDS)
    return 0


def _attach(args: argparse.Namespace, desktop: Desktop, folder: Path) -> int:
    """Show the program that already runs on this data folder, once it answers."""
    address = _address(load_or_create(folder / "rhinvoice.json").port)
    deadline = time.monotonic() + ATTACH_SECONDS
    if not wait_until_answers(address, running=lambda: time.monotonic() < deadline):
        return _failed(OSError(f"Rhinvoice runs already, but does not answer on {address}"))
    _show(args, desktop, address, folder)
    return 0


def _show(args: argparse.Namespace, desktop: Desktop, address: str, folder: Path) -> None:
    if args.no_browser:
        return
    if args.browser or desktop.show_window is None:
        desktop.open_page(address)
    else:
        desktop.show_window(address, folder / "window")


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


def when_ready(
    address: str,
    folder: Path,
    open_page: Callable[[str], object] | None = None,
    running: Callable[[], bool] = lambda: True,
) -> bool:
    """Wait for the web interface; then tell the boot that this version works and open it.

    Tell whether it answered while ``running``. An update that never gets here is taken back.
    """
    if not wait_until_answers(address, running):
        return False
    confirm(folder)
    if open_page is not None:
        open_page(address)
    return True


def wait_until_answers(address: str, running: Callable[[], bool]) -> bool:
    """Wait for the web interface as long as ``running``; tell whether it answered."""
    while running():
        if answers(address):
            return True
        time.sleep(READY_POLL_SECONDS)
    return False
