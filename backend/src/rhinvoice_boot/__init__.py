"""Start the app package that fits this runtime; take back an update that fails (ADR 0022).

Part of the runtime that the setup installs, beside Python and PostgreSQL, and therefore
kept small and stable: it changes only with a new setup, while the app packages it starts
change with every update. It knows nothing of Rhinvoice but the launcher's name and the
files described here; it uses the standard library only.

    <install>/runtime.json            {"generation": 1}
    <install>/app/                    the app package the setup brought
    <data>/app/versions/<version>/    app packages of updates
    <data>/app/state.json             which one runs, and whether it still has to prove itself
    <data>/backups/                   copies of the database folder before each update

An app package holds ``site-packages/``, ``static/`` and ``manifest.json``
({"version": "0.7.0", "runtime": 1}: the runtime generation it needs at least).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import site
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence

KEEP = 3
"""App packages of updates and database copies kept for going back (ADR 0022)."""
RETRIES = 10
RETRY_PAUSE_SECONDS = 0.5
SESSION = "RHINVOICE_BOOT_SESSION"
"""Set in the environment of a boot that runs inside the session of its parent."""
RESTART = 75
"""Exit code with which the program asks to be started again (after an update)."""
LAUNCHER = "rhinvoice.desktop.launcher"
NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)
"""Windows opens a console window for every command-line tool a program without a console
starts (Rhinvoice.exe); this flag keeps them hidden. 0 elsewhere."""
NOT_RUNNING = 3
"""Exit code of ``pg_ctl status`` when no server runs on the data folder."""


class BootError(Exception):
    """No app package can be started."""


def data_folder(system: str, environ: Mapping[str, str], home: Path) -> Path:
    """Return the folder for the database, the configuration and the logs of this user.

    ``system`` is ``platform.system()``. Backups must include this folder.
    """
    if system == "Windows":
        return Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "Rhinvoice"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Rhinvoice"
    return Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "rhinvoice"


def make_private(folder: Path) -> None:
    """Create a folder that only this user can open.

    On Windows the folders below %LOCALAPPDATA% are the user's own already. There Python
    turns 0o700 into an access list that the database's tools cannot pass: they run with
    restricted rights (PostgreSQL does that on purpose).
    """
    folder.mkdir(mode=0o777 if sys.platform == "win32" else 0o700, parents=True, exist_ok=True)


def version_key(version: str) -> tuple[int, ...]:
    """Order versions like 0.10.0 after 0.9.1; anything else is not a version."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return ()


@dataclass(frozen=True, slots=True)
class Package:
    version: str
    folder: Path
    runtime: int


@dataclass(frozen=True, slots=True)
class State:
    active: str | None = None
    """The version that last answered: the one to go back to."""
    trying: str | None = None
    """A version on its first start: it is taken back if it ends before it answered."""
    saved: bool = False
    """The database was copied before the first start of ``trying``."""
    failed: list[str] = field(default_factory=list[str])
    """Versions that did not start after an update; never chosen again."""
    restore: str | None = None
    """The database from before this version still has to be put back (a take-back that
    could not finish, e.g. a file Windows kept locked): done before anything starts."""


def state_file(data: Path) -> Path:
    return data / "app" / "state.json"


def load_state(data: Path) -> State:
    """Read the state; a missing or damaged file means: nothing ran yet."""
    try:
        values = json.loads(state_file(data).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return State()
    if not isinstance(values, dict):
        return State()
    fields = cast("dict[str, object]", values)
    active, trying, restore = fields.get("active"), fields.get("trying"), fields.get("restore")
    saved, failed = fields.get("saved", False), fields.get("failed", [])
    if (
        not isinstance(active, str | None)
        or not isinstance(trying, str | None)
        or not isinstance(restore, str | None)
        or not isinstance(saved, bool)
        or not isinstance(failed, list)
    ):
        return State()
    versions = [str(version) for version in cast("list[object]", failed)]
    return State(active, trying, saved=saved, failed=versions, restore=restore)


def save_state(data: Path, state: State) -> None:
    path = state_file(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def confirm(data: Path) -> None:
    """Record that the running version works (called by it once its interface answers).

    Part of the interface that app packages use (see ADR 0022): keep its name and meaning.
    """
    state = load_state(data)
    if state.trying is not None:
        save_state(data, replace(state, active=state.trying, trying=None, saved=False))
        prune(data, state.trying)


def prune(data: Path, active: str, keep: int = KEEP) -> None:
    """Keep the last ``keep`` app packages of updates and database copies; remove the rest."""
    versions = data / "app" / "versions"
    found: list[Path] = list(versions.iterdir()) if versions.is_dir() else []
    packages = [
        folder
        for folder in found
        if folder.is_dir() and folder.suffix != ".partial" and folder.name != active
    ]
    _remove_oldest(packages, "", keep)
    backups = data / "backups"
    for kind in ("database-before-", "database-failed-"):
        copies = [f for f in backups.glob(f"{kind}*") if f.is_dir()] if backups.is_dir() else []
        _remove_oldest(copies, kind, keep)


def _remove_oldest(folders: list[Path], prefix: str, keep: int) -> None:
    """Remove all but the ``keep`` newest folders named ``<prefix><version>``."""
    ordered = sorted(folders, key=lambda folder: version_key(folder.name.removeprefix(prefix)))
    for folder in ordered[: max(len(ordered) - keep, 0)]:
        shutil.rmtree(folder, ignore_errors=True)


def runtime_generation(install: Path) -> int:
    path = install / "runtime.json"
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["generation"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        msg = f"{path} is missing or damaged: the setup has to be run again"
        raise BootError(msg) from error


def read_package(folder: Path) -> Package | None:
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        package = Package(str(manifest["version"]), folder, int(manifest["runtime"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return package if version_key(package.version) else None


def packages(install: Path, data: Path) -> list[Package]:
    """List the app packages that this runtime can start, newest first."""
    generation = runtime_generation(install)
    versions = data / "app" / "versions"
    folders = [install / "app"]
    if versions.is_dir():
        # A ".partial" folder is a download that did not finish.
        folders += [folder for folder in versions.iterdir() if folder.suffix != ".partial"]
    found = [package for folder in folders if (package := read_package(folder))]
    usable = [package for package in found if package.runtime <= generation]
    return sorted(usable, key=lambda package: version_key(package.version), reverse=True)


def choose(install: Path, data: Path, state: State) -> Package:
    """Take the newest package that fits and did not fail, from the setup or an update."""
    candidates = [p for p in packages(install, data) if p.version not in state.failed]
    if not candidates:
        msg = f"no app package fits the runtime in {install}"
        raise BootError(msg)
    return candidates[0]


@dataclass(frozen=True, slots=True)
class Runtime:
    """The surroundings of the boot; tests replace the program and the restart."""

    install: Path
    data: Path
    launch: Callable[[Package, list[str]], int]
    restart: Callable[[], int]
    """Starts the boot anew in a new process and returns its exit code."""


def run(argv: Sequence[str], runtime: Runtime) -> int:
    with session(runtime.data) as owner:
        if not owner:
            # Started again while it runs (or migrates): only show the running program.
            package = choose(runtime.install, runtime.data, load_state(runtime.data))
            return runtime.launch(package, [*argv, *_folders(runtime, package), "--attach"])
        return _run_session(argv, runtime)


def _run_session(argv: Sequence[str], runtime: Runtime) -> int:
    state = load_state(runtime.data)
    if state.restore is not None:
        state = put_database_back(runtime, state)
    if maintenance(argv):
        # Never the trial of an update: such a run does not confirm a version, and
        # taking it back would put the old database over a restored one.
        package = (
            choose(runtime.install, runtime.data, state)
            if state.active is None
            else _package_of(runtime, state)
        )
        return runtime.launch(package, [*argv, *_folders(runtime, package)])
    package = choose(runtime.install, runtime.data, state)
    if package.version != state.active and not (state.trying == package.version and state.saved):
        try:
            copy_database(runtime, f"before-{package.version}")
        except (OSError, subprocess.CalledProcessError) as error:
            # No copy, no update: the version that ran before starts instead.
            sys.stderr.write(f"error: no copy of the database before {package.version}: {error}\n")
            package = _package_of(runtime, state)
        else:
            state = replace(state, trying=package.version, saved=True)
            save_state(runtime.data, state)
    try:
        code = runtime.launch(package, [*argv, *_folders(runtime, package)])
    except Exception:  # noqa: BLE001 - a broken package must not keep the previous one from starting
        traceback.print_exc()
        code = 1
    # Only an update is taken back: without a version that ran before, there is none to
    # go back to, and the next start tries again (it may have been the computer, not us).
    if load_state(runtime.data).trying == package.version and state.active is not None:
        take_back(runtime, package.version)
        return runtime.restart()
    if code == RESTART:
        return runtime.restart()
    return code


def _folders(runtime: Runtime, package: Package) -> list[str]:
    return [
        "--install-dir", str(runtime.install),
        "--static-dir", str(package.folder / "static"),
        "--data-dir", str(runtime.data),
    ]  # fmt: skip


def _package_of(runtime: Runtime, state: State) -> Package:
    """Find the package of the version that ran before."""
    for package in packages(runtime.install, runtime.data):
        if package.version == state.active:
            return package
    msg = f"the version that ran before ({state.active}) is no longer installed"
    raise BootError(msg)


def take_back(runtime: Runtime, version: str) -> None:
    """Never choose the failed version again, and put back the database from before it."""
    state = load_state(runtime.data)
    saved = runtime.data / "backups" / f"database-before-{version}"
    # The decision is written first: if putting the database back fails, the next start
    # tries again before anything runs, and the failed version never starts again.
    state = replace(
        state,
        trying=None,
        saved=False,
        failed=[*state.failed, version],
        restore=version if saved.is_dir() else None,
    )
    save_state(runtime.data, state)
    if state.restore is not None:
        put_database_back(runtime, state)


def put_database_back(runtime: Runtime, state: State) -> State:
    """Replace the database with the copy from before ``state.restore``; keep the other aside."""
    version = state.restore
    saved = runtime.data / "backups" / f"database-before-{version}"
    database = runtime.data / "database"
    failed = runtime.data / "backups" / f"database-failed-{version}"
    try:
        stop_database(runtime)
        if failed.exists():
            retry(lambda: shutil.rmtree(failed))
        if database.exists():
            retry(lambda: database.rename(failed))
        shutil.copytree(saved, database)
    except (OSError, subprocess.CalledProcessError) as error:
        msg = (
            f"the database from before {version} could not be put back ({error}); "
            f"the copy is in {saved}"
        )
        raise BootError(msg) from error
    state = replace(state, restore=None)
    save_state(runtime.data, state)
    return state


def retry(action: Callable[[], object], attempts: int = RETRIES) -> None:
    """Repeat a file operation that Windows may refuse while a scanner holds a file."""
    for _ in range(attempts - 1):
        try:
            action()
        except OSError:
            time.sleep(RETRY_PAUSE_SECONDS)
        else:
            return
    action()  # the last attempt: its error is the answer


def copy_database(runtime: Runtime, name: str) -> None:
    """Copy the stopped database folder into the backups."""
    database = runtime.data / "database"
    if not database.is_dir():
        return
    stop_database(runtime)
    target = runtime.data / "backups" / f"database-{name}"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(database, target)


@contextmanager
def session(data: Path) -> Generator[bool]:
    """Hold the data folder for this program; yield whether this boot got it.

    A boot started by its parent (a restart) runs in the parent's session.
    """
    if os.environ.get(SESSION) == "1":
        yield True
        return
    make_private(data)
    folder = data / "app"
    folder.mkdir(exist_ok=True)
    with (folder / "session.lock").open("a+b") as handle:
        if not _lock(handle):
            yield False
            return
        os.environ[SESSION] = "1"
        try:
            yield True
        finally:
            del os.environ[SESSION]


def _lock(handle: BinaryIO) -> bool:
    """Take the lock without waiting; the system releases it when this process ends."""
    try:
        if sys.platform == "win32":  # pragma: no cover - the CI smoke test runs this on Windows
            import msvcrt  # noqa: PLC0415

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # noqa: PLC0415

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def stop_database(runtime: Runtime) -> None:
    """Stop a server left running on the data folder (the program normally stops it)."""
    if not (runtime.data / "database" / "PG_VERSION").exists():
        return
    pg_ctl = str(runtime.install / "postgresql" / "bin" / "pg_ctl")
    pgdata = f"--pgdata={runtime.data / 'database'}"
    status = subprocess.run(  # noqa: S603 - the bundled tool
        [pg_ctl, "status", pgdata], capture_output=True, check=False, creationflags=NO_WINDOW
    )
    if status.returncode != NOT_RUNNING:
        stop = [pg_ctl, "stop", "--wait", "--mode=fast", pgdata]
        subprocess.run(stop, capture_output=True, check=True, creationflags=NO_WINDOW)  # noqa: S603 - the bundled tool


def launch(package: Package, arguments: list[str], module: str = LAUNCHER) -> int:
    """Run the package's launcher in this process."""
    # As a site folder, so that the .pth files of its libraries apply; first on the path.
    before = list(sys.path)
    site.addsitedir(str(package.folder / "site-packages"))
    sys.path[:] = [entry for entry in sys.path if entry not in before] + before
    main: Callable[[list[str]], int] = __import__(module, fromlist=["main"]).main
    return main(arguments)


def restart() -> int:
    """Start the boot anew and wait for it: it reads the state and imports a package afresh.

    A child, not a replacement: on Windows a replaced process would lose the setup's
    shortcut, the console and the request to close. A request to end (Ctrl+C, Windows'
    CTRL_BREAK) reaches the child, which stops its server and database; meanwhile this
    process ignores it, as stopping here would kill the child in the middle of that.
    """
    ignored = [s for s in (signal.SIGINT, getattr(signal, "SIGBREAK", None)) if s is not None]
    previous = {number: signal.signal(number, signal.SIG_IGN) for number in ignored}
    try:
        return subprocess.call([sys.executable, "-m", "rhinvoice_boot", *sys.argv[1:]])  # noqa: S603 - this program
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def option(argv: Sequence[str], name: str) -> str | None:
    """Find the value of ``--name value`` or ``--name=value``."""
    for index, argument in enumerate(argv):
        if argument == name and index + 1 < len(argv):
            return argv[index + 1]
        if argument.startswith(f"{name}="):
            return argument.split("=", 1)[1]
    return None


MAINTENANCE = ("--restore", "--list-backups")
"""Options that run a task of the program and end, without serving (backups, ADR 0023)."""


def maintenance(argv: Sequence[str]) -> bool:
    """Tell whether the program is started for a task, not to serve."""
    return any(
        argument == name or argument.startswith(f"{name}=")
        for argument in argv
        for name in MAINTENANCE
    )


def without_option(argv: Sequence[str], name: str) -> list[str]:
    """Remove ``--name value`` and ``--name=value`` (the boot passes its own)."""
    kept: list[str] = []
    skip = False
    for argument in argv:
        if skip:
            skip = False
        elif argument == name:
            skip = True
        elif not argument.startswith(f"{name}="):
            kept.append(argument)
    return kept


def log_without_console(data: Path) -> None:
    """Write the messages to rhinvoice.log when there is no console (Rhinvoice.exe)."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    make_private(data)
    log = (data / "rhinvoice.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    given = option(arguments, "--data-dir")
    data = Path(given) if given else data_folder(platform.system(), os.environ, Path.home())
    log_without_console(data)
    # The bundled interpreter lives in <install>/python.
    runtime = Runtime(Path(sys.prefix).parent, data, launch, restart)
    try:
        return run(without_option(arguments, "--data-dir"), runtime)
    except BootError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
