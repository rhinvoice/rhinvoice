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
import subprocess
import sys
import traceback
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

RESTART = 75
"""Exit code with which the program asks to be started again (after an update)."""
LAUNCHER = "rhinvoice.desktop.launcher"
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
    """The version to start; None: the newest that fits."""
    previous: str | None = None
    """The version that ran before the active one (to go back to)."""
    pending: bool = False
    """The active version has not yet answered once: it is taken back if it ends before."""
    saved: bool = False
    """The database was copied before the pending version's first start."""
    failed: list[str] = field(default_factory=list[str])
    """Versions that did not start; never chosen again."""


def state_file(data: Path) -> Path:
    return data / "app" / "state.json"


def load_state(data: Path) -> State:
    """Read the state; a missing or damaged file means: start the newest package."""
    try:
        values = json.loads(state_file(data).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return State()
    if not isinstance(values, dict):
        return State()
    fields = cast("dict[str, object]", values)
    active, previous, failed = (
        fields.get("active"),
        fields.get("previous"),
        fields.get("failed", []),
    )
    pending, saved = fields.get("pending", False), fields.get("saved", False)
    if (
        not isinstance(active, str | None)
        or not isinstance(previous, str | None)
        or not isinstance(pending, bool)
        or not isinstance(saved, bool)
        or not isinstance(failed, list)
    ):
        return State()
    versions = [str(version) for version in cast("list[object]", failed)]
    return State(active, previous, pending=pending, saved=saved, failed=versions)


def save_state(data: Path, state: State) -> None:
    path = state_file(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def confirm(data: Path) -> None:
    """Record that the running version works (called by it once its interface answers)."""
    state = load_state(data)
    if state.pending:
        save_state(data, replace(state, pending=False))


def switch_to(data: Path, version: str) -> None:
    """Start ``version`` next time; it has to prove itself (called by the updater)."""
    state = load_state(data)
    save_state(
        data, replace(state, active=version, previous=state.active, pending=True, saved=False)
    )


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
    candidates = [p for p in packages(install, data) if p.version not in state.failed]
    if not candidates:
        msg = f"no app package fits the runtime in {install}"
        raise BootError(msg)
    active = [package for package in candidates if package.version == state.active]
    return (active or candidates)[0]


@dataclass(frozen=True, slots=True)
class Runtime:
    """The surroundings of the boot; tests replace the program and the restart."""

    install: Path
    data: Path
    launch: Callable[[Package, list[str]], int]
    restart: Callable[[], None]


def run(argv: Sequence[str], runtime: Runtime) -> int:
    state = load_state(runtime.data)
    package = choose(runtime.install, runtime.data, state)
    proving = state.pending and state.active == package.version
    if proving and not state.saved:
        copy_database(runtime, f"before-{package.version}")
        state = replace(state, saved=True)
        save_state(runtime.data, state)
    arguments = [
        *argv,
        "--install-dir", str(runtime.install),
        "--static-dir", str(package.folder / "static"),
        "--data-dir", str(runtime.data),
    ]  # fmt: skip
    try:
        code = runtime.launch(package, arguments)
    except Exception:  # noqa: BLE001 - a broken package must not keep the previous one from starting
        traceback.print_exc()
        code = 1
    if proving and load_state(runtime.data).pending:
        take_back(runtime, package.version)
        runtime.restart()
        return code
    if code == RESTART:
        runtime.restart()
    return code


def take_back(runtime: Runtime, version: str) -> None:
    """Return to the previous version and the database as it was before the update."""
    state = load_state(runtime.data)
    stop_database(runtime)
    database = runtime.data / "database"
    saved = runtime.data / "backups" / f"database-before-{version}"
    if saved.is_dir():
        failed = runtime.data / "backups" / f"database-failed-{version}"
        shutil.rmtree(failed, ignore_errors=True)
        if database.exists():
            database.rename(failed)
        shutil.copytree(saved, database)
    save_state(
        runtime.data,
        State(
            active=state.previous,
            previous=None,
            pending=False,
            saved=False,
            failed=[*state.failed, version],
        ),
    )


def copy_database(runtime: Runtime, name: str) -> None:
    """Copy the stopped database folder into the backups."""
    database = runtime.data / "database"
    if not database.is_dir():
        return
    stop_database(runtime)
    target = runtime.data / "backups" / f"database-{name}"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(database, target)


def stop_database(runtime: Runtime) -> None:
    """Stop a server left running on the data folder (the program normally stops it)."""
    if not (runtime.data / "database" / "PG_VERSION").exists():
        return
    pg_ctl = str(runtime.install / "postgresql" / "bin" / "pg_ctl")
    pgdata = f"--pgdata={runtime.data / 'database'}"
    status = subprocess.run([pg_ctl, "status", pgdata], capture_output=True, check=False)  # noqa: S603 - the bundled tool
    if status.returncode != NOT_RUNNING:
        stop = [pg_ctl, "stop", "--wait", "--mode=fast", pgdata]
        subprocess.run(stop, capture_output=True, check=True)  # noqa: S603 - the bundled tool


def launch(package: Package, arguments: list[str], module: str = LAUNCHER) -> int:
    """Run the package's launcher in this process."""
    sys.path.insert(0, str(package.folder / "site-packages"))
    main: Callable[[list[str]], int] = __import__(module, fromlist=["main"]).main
    return main(arguments)


def restart() -> None:
    """Replace this process with a new start of the boot (it reads the state anew)."""
    os.execv(sys.executable, [sys.executable, "-m", "rhinvoice_boot", *sys.argv[1:]])  # noqa: S606 - this program


def option(argv: Sequence[str], name: str) -> str | None:
    """Find the value of ``--name value`` or ``--name=value``."""
    for index, argument in enumerate(argv):
        if argument == name and index + 1 < len(argv):
            return argv[index + 1]
        if argument.startswith(f"{name}="):
            return argument.split("=", 1)[1]
    return None


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


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    given = option(arguments, "--data-dir")
    data = Path(given) if given else data_folder(platform.system(), os.environ, Path.home())
    # The bundled interpreter lives in <install>/python.
    runtime = Runtime(Path(sys.prefix).parent, data, launch, restart)
    try:
        return run(without_option(arguments, "--data-dir"), runtime)
    except BootError as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
