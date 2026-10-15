"""The boot of the runtime: which app package starts, and how a failed update is taken back."""

import importlib
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

import rhinvoice_boot as boot
from rhinvoice.desktop.launcher import build_parser as launcher_parser
from rhinvoice.desktop.postgres import BundledPostgres
from rhinvoice_boot import (
    RESTART,
    SESSION,
    BootError,
    Package,
    Runtime,
    State,
    choose,
    confirm,
    load_state,
    log_without_console,
    option,
    packages,
    prune,
    run,
    save_state,
    session,
    version_key,
    without_option,
)
from tests.helpers import raises_exactly
from tests.unit.desktop.tools import commands

PREFIX_BEFORE = os.environ.get("PYTHONPYCACHEPREFIX")
"""As the test process started; the tests of main() must leave it so."""


def package(folder: Path, version: str, runtime: int = 1) -> Path:
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"version": version, "runtime": runtime}))
    return folder


@pytest.fixture
def runtime_folder(install: Path) -> Path:
    """Make the setup's folder: runtime generation 1 with the app package 0.6.2."""
    (install / "runtime.json").write_text(json.dumps({"generation": 1}))
    package(install / "app", "0.6.2")
    return install


@pytest.fixture
def data(tmp_path: Path) -> Path:
    return tmp_path / "data"


def update(data: Path, version: str, runtime: int = 1) -> Path:
    return package(data / "app" / "versions" / version, version, runtime)


class Program:
    """Stands in for the launcher; records its starts and may confirm itself."""

    def __init__(self, data: Path, *, works: bool = True, code: int = 0) -> None:
        self.data = data
        self.works = works
        self.code = code
        self.started: list[tuple[str, list[str]]] = []
        self.restarts = 0

    def launch(self, chosen: Package, arguments: list[str]) -> int:
        self.started.append((chosen.version, arguments))
        if self.works:
            confirm(self.data)
        return self.code

    def restart(self) -> int:
        self.restarts += 1
        return self.code


def runtime(install: Path, data: Path, program: Program) -> Runtime:
    return Runtime(install, data, program.launch, program.restart)


def test_versions_are_ordered_by_their_numbers() -> None:
    assert version_key("0.10.0") > version_key("0.9.1") > version_key("0.9")
    assert version_key("0.7.0-beta") == ()


def test_the_newest_package_that_fits_the_runtime_is_chosen(
    runtime_folder: Path, data: Path
) -> None:
    update(data, "0.7.0")
    update(data, "0.10.0", runtime=2)  # needs a new setup
    (data / "app" / "versions" / "0.8.0.partial").mkdir()  # a download that did not finish
    (data / "app" / "versions" / "broken").mkdir()  # no manifest
    package(data / "app" / "versions" / "beta", "0.9.0-beta")  # not a version
    found = packages(runtime_folder, data)
    assert [p.version for p in found] == ["0.7.0", "0.6.2"]
    assert choose(runtime_folder, data, State()).version == "0.7.0"
    # One that failed is never chosen again, also when it is the newest.
    assert choose(runtime_folder, data, State(failed=["0.7.0"])).version == "0.6.2"


def test_a_newer_setup_wins_over_an_older_update(runtime_folder: Path, data: Path) -> None:
    update(data, "0.6.1")
    assert choose(runtime_folder, data, State(active="0.6.1")).version == "0.6.2"


def test_without_a_fitting_package_nothing_starts(runtime_folder: Path, data: Path) -> None:
    with raises_exactly(BootError, f"no app package fits the runtime in {runtime_folder}"):
        choose(runtime_folder, data, State(failed=["0.6.2"]))


def test_a_runtime_without_its_description_asks_for_the_setup(install: Path, data: Path) -> None:
    path = install / "runtime.json"
    with raises_exactly(BootError, f"{path} is missing or damaged: the setup has to be run again"):
        packages(install, data)


@pytest.mark.parametrize(
    "content",
    ["{", "[]", '{"active": 1}', '{"trying": 1}', '{"saved": "yes"}', '{"failed": "0.7.0"}'],
)
def test_a_damaged_state_counts_as_nothing_ran_yet(data: Path, content: str) -> None:
    (data / "app").mkdir(parents=True)
    (data / "app" / "state.json").write_text(content)
    assert load_state(data) == State()


def test_the_state_is_kept_between_starts(data: Path) -> None:
    assert load_state(data) == State()
    state = State(active="0.6.2", trying="0.7.0", saved=True, failed=["0.6.9"])
    save_state(data, state)
    assert load_state(data) == state


def test_a_version_on_its_first_start_proves_itself_once(data: Path) -> None:
    save_state(data, State(active="0.6.2", trying="0.7.0", saved=True))
    confirm(data)
    assert load_state(data) == State(active="0.7.0")
    confirm(data)  # nothing left to confirm
    assert load_state(data) == State(active="0.7.0")


def test_the_chosen_package_is_started_with_its_folders(runtime_folder: Path, data: Path) -> None:
    program = Program(data)
    assert run(["--no-browser"], runtime(runtime_folder, data, program)) == 0
    assert program.started == [
        (
            "0.6.2",
            [
                "--no-browser",
                "--install-dir", str(runtime_folder),
                "--static-dir", str(runtime_folder / "app" / "static"),
                "--data-dir", str(data),
            ],
        )
    ]  # fmt: skip
    assert program.restarts == 0
    assert load_state(data) == State(active="0.6.2")


def test_a_first_installation_that_fails_is_tried_again(runtime_folder: Path, data: Path) -> None:
    program = Program(data, works=False, code=1)
    assert run([], runtime(runtime_folder, data, program)) == 1
    # There is no version to go back to: nothing is taken back or marked as failed.
    assert program.restarts == 0
    assert load_state(data).failed == []
    run([], runtime(runtime_folder, data, Program(data)))
    assert load_state(data) == State(active="0.6.2")


def test_the_program_may_ask_to_be_started_again(runtime_folder: Path, data: Path) -> None:
    program = Program(data, code=RESTART)
    assert run([], runtime(runtime_folder, data, program)) == RESTART
    assert program.restarts == 1


def database(install: Path, data: Path) -> BundledPostgres:
    return BundledPostgres(install / "postgresql" / "bin", data / "database", "secret", 5432)


def installed(runtime_folder: Path, data: Path) -> None:
    """Run 0.6.2 once, with a database that holds invoices."""
    run([], runtime(runtime_folder, data, Program(data)))
    postgres = database(runtime_folder, data)
    postgres.start()
    postgres.stop()
    (data / "database" / "invoices").write_text("before the update")


def test_an_update_that_works_keeps_a_copy_of_the_database_from_before(
    runtime_folder: Path, data: Path, tmp_path: Path
) -> None:
    installed(runtime_folder, data)
    database(runtime_folder, data).start()  # left running by the version that downloaded it
    update(data, "0.7.0")
    program = Program(data)
    assert run([], runtime(runtime_folder, data, program)) == 0
    assert [version for version, _ in program.started] == ["0.7.0"]
    copy = data / "backups" / "database-before-0.7.0"
    assert (copy / "invoices").read_text() == "before the update"
    # The copy is taken of the stopped database.
    assert commands(tmp_path)[-2:] == ["pg_ctl status", "pg_ctl stop"]
    assert load_state(data) == State(active="0.7.0")
    # Later starts of the same version copy nothing.
    shutil.rmtree(copy)
    run([], runtime(runtime_folder, data, Program(data)))
    assert not copy.exists()


def test_an_update_that_fails_is_taken_back_with_its_database(
    runtime_folder: Path, data: Path
) -> None:
    installed(runtime_folder, data)
    update(data, "0.7.0")

    class Migrating(Program):
        def launch(self, chosen: Package, arguments: list[str]) -> int:
            # The new version changes the database, then fails before it answers.
            (self.data / "database" / "invoices").write_text("half migrated")
            return super().launch(chosen, arguments)

    program = Migrating(data, works=False, code=1)
    assert run([], runtime(runtime_folder, data, program)) == 1
    assert program.restarts == 1
    assert (data / "database" / "invoices").read_text() == "before the update"
    failed = data / "backups" / "database-failed-0.7.0"
    assert (failed / "invoices").read_text() == "half migrated"
    assert load_state(data) == State(active="0.6.2", failed=["0.7.0"])
    # The next start runs the previous version again.
    assert choose(runtime_folder, data, load_state(data)).version == "0.6.2"


@pytest.mark.parametrize(
    "maintenance",
    [["--restore", "latest"], ["--restore=4f3a9c1e"], ["--list-backups"]],
)
def test_a_restore_runs_with_the_version_that_runs_and_is_never_taken_back(
    runtime_folder: Path, data: Path, maintenance: list[str]
) -> None:
    """A restore never confirms a version: it must not count as the trial of an update."""
    installed(runtime_folder, data)
    update(data, "0.7.0")  # downloaded, not started yet

    class Restoring(Program):
        def launch(self, chosen: Package, arguments: list[str]) -> int:
            (self.data / "database" / "invoices").write_text("restored")
            return super().launch(chosen, arguments)

    program = Restoring(data, works=False)
    assert run(maintenance, runtime(runtime_folder, data, program)) == 0
    assert [version for version, _ in program.started] == ["0.6.2"]
    assert program.started[0][1][: len(maintenance)] == maintenance
    assert program.restarts == 0
    assert (data / "database" / "invoices").read_text() == "restored"
    assert not (data / "backups" / "database-before-0.7.0").exists()
    assert load_state(data) == State(active="0.6.2")
    # The update is still tried at the next normal start.
    assert choose(runtime_folder, data, load_state(data)).version == "0.7.0"


def test_a_restore_on_a_fresh_installation_uses_the_installed_version(
    runtime_folder: Path, data: Path
) -> None:
    program = Program(data, works=False)
    assert run(["--restore", "latest"], runtime(runtime_folder, data, program)) == 0
    assert [version for version, _ in program.started] == ["0.6.2"]
    assert load_state(data) == State()


def test_an_update_without_a_database_yet_is_taken_back_without_one(
    runtime_folder: Path, data: Path
) -> None:
    run([], runtime(runtime_folder, data, Program(data)))
    update(data, "0.7.0")
    run([], runtime(runtime_folder, data, Program(data, works=False, code=1)))
    assert not (data / "database").exists()
    assert load_state(data) == State(active="0.6.2", failed=["0.7.0"])


def test_a_failed_update_whose_database_vanished_gets_the_copy_back(
    runtime_folder: Path, data: Path
) -> None:
    installed(runtime_folder, data)
    update(data, "0.7.0")

    class Deleting(Program):
        def launch(self, chosen: Package, arguments: list[str]) -> int:
            shutil.rmtree(self.data / "database")
            return super().launch(chosen, arguments)

    run([], runtime(runtime_folder, data, Deleting(data, works=False, code=1)))
    assert (data / "database" / "invoices").read_text() == "before the update"


def test_an_interrupted_first_start_does_not_copy_the_database_again(
    runtime_folder: Path, data: Path
) -> None:
    installed(runtime_folder, data)
    update(data, "0.7.0")
    # The computer went off during the first start of 0.7.0, after the copy.
    save_state(data, State(active="0.6.2", trying="0.7.0", saved=True))
    copy = data / "backups" / "database-before-0.7.0"
    run([], runtime(runtime_folder, data, Program(data)))
    assert not copy.exists()
    assert load_state(data) == State(active="0.7.0")


def test_the_launcher_of_the_package_runs_in_this_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "package"
    (folder / "site-packages").mkdir(parents=True)
    (folder / "site-packages" / "boot_test_launcher.py").write_text(
        "def main(arguments):\n    return len(arguments)\n"
    )
    monkeypatch.setattr(sys, "path", list(sys.path))
    chosen = Package("0.7.0", folder, 1)
    assert boot.launch(chosen, ["a", "b"], module="boot_test_launcher") == 2
    assert sys.path[0] == str(folder / "site-packages")


@pytest.mark.parametrize("windows", [False, True])
def test_a_restart_runs_the_boot_anew_and_waits_for_it(
    monkeypatch: pytest.MonkeyPatch,
    windows: bool,
) -> None:
    if windows:  # Windows' CTRL_BREAK, here stood in for by SIGUSR1
        monkeypatch.setattr(signal, "SIGBREAK", signal.SIGUSR1, raising=False)
    else:
        monkeypatch.delattr(signal, "SIGBREAK", raising=False)
    calls: list[list[str]] = []
    ignored: list[bool] = []

    def call(arguments: list[str]) -> int:
        calls.append(arguments)
        # While the child runs, a request to end is the child's to handle.
        ignored.append(signal.getsignal(signal.SIGINT) is signal.SIG_IGN)
        if windows:
            ignored.append(signal.getsignal(signal.SIGUSR1) is signal.SIG_IGN)
        return 7

    monkeypatch.setattr(subprocess, "call", call)
    monkeypatch.setattr(sys, "argv", ["rhinvoice_boot", "--browser"])
    assert boot.restart() == 7
    assert calls == [[sys.executable, "-m", "rhinvoice_boot", "--browser"]]
    assert ignored == ([True, True] if windows else [True])
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


def test_options_are_read_in_both_spellings() -> None:
    assert option(["--data-dir", "/d"], "--data-dir") == "/d"
    assert option(["--data-dir=/d"], "--data-dir") == "/d"
    assert option(["--data-dir"], "--data-dir") is None
    assert option([], "--data-dir") is None
    assert without_option(["--data-dir", "/d", "--browser"], "--data-dir") == ["--browser"]
    assert without_option(["--browser", "--data-dir=/d"], "--data-dir") == ["--browser"]


@pytest.fixture
def bytecode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the bytecode settings of this test process as they are."""
    monkeypatch.setattr(sys, "pycache_prefix", sys.pycache_prefix)
    # Set first, so that monkeypatch records the variable and removes what main() sets.
    monkeypatch.setenv("PYTHONPYCACHEPREFIX", "")
    monkeypatch.delenv("PYTHONPYCACHEPREFIX")


@pytest.mark.parametrize(
    ("system", "environ", "folder"),
    [
        (
            "Windows",
            {"LOCALAPPDATA": "C:/Users/anna/AppData/Local"},
            Path("C:/Users/anna/AppData/Local/Rhinvoice/cache/pycache"),
        ),
        ("Windows", {}, Path("/home/anna/AppData/Local/Rhinvoice/cache/pycache")),
        ("Darwin", {}, Path("/home/anna/Library/Caches/Rhinvoice/pycache")),
        ("Linux", {"XDG_CACHE_HOME": "/var/cache/anna"}, Path("/var/cache/anna/rhinvoice/pycache")),
        ("Linux", {}, Path("/home/anna/.cache/rhinvoice/pycache")),
    ],
)
def test_compiled_python_files_go_to_the_users_cache(
    system: str, environ: dict[str, str], folder: Path
) -> None:
    """Never into the program folder: on macOS it is signed, and a write would break the seal."""
    assert boot.bytecode_cache(system, environ, Path("/home/anna")) == folder


@pytest.mark.usefixtures("bytecode")
def test_the_bytecode_cache_applies_here_and_to_the_programs_started_later(
    tmp_path: Path,
) -> None:
    environ: dict[str, str] = {}
    boot.use_bytecode_cache(environ, tmp_path / "cache")
    assert environ == {"PYTHONPYCACHEPREFIX": str(tmp_path / "cache")}
    assert sys.pycache_prefix == str(tmp_path / "cache")
    # Set already by the start script (macOS): kept.
    given = {"PYTHONPYCACHEPREFIX": "/Users/anna/Library/Caches/Rhinvoice/pycache"}
    boot.use_bytecode_cache(given, tmp_path / "other")
    assert sys.pycache_prefix == "/Users/anna/Library/Caches/Rhinvoice/pycache"
    # Set but empty: Python would write next to the program files (a relative prefix).
    empty = {"PYTHONPYCACHEPREFIX": ""}
    boot.use_bytecode_cache(empty, tmp_path / "cache")
    assert empty == {"PYTHONPYCACHEPREFIX": str(tmp_path / "cache")}
    assert sys.pycache_prefix == str(tmp_path / "cache")


@pytest.mark.usefixtures("bytecode")
def test_main_starts_from_the_interpreter_of_the_runtime(
    runtime_folder: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = Program(data)
    monkeypatch.setattr(sys, "prefix", str(runtime_folder / "python"))
    monkeypatch.setattr(boot, "launch", program.launch)
    assert boot.main(["--data-dir", str(data), "--no-browser"]) == 0
    [(_version, arguments)] = program.started
    assert arguments[:3] == ["--no-browser", "--install-dir", str(runtime_folder)]
    assert os.environ["PYTHONPYCACHEPREFIX"] == sys.pycache_prefix


@pytest.mark.usefixtures("bytecode")
def test_main_reports_a_runtime_it_cannot_use(
    install: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "prefix", str(install / "python"))
    monkeypatch.setattr(sys, "argv", ["rhinvoice_boot"])
    monkeypatch.setenv("XDG_DATA_HOME", str(install / "home"))
    monkeypatch.setenv("HOME", str(install / "home"))
    assert boot.main() == 1
    assert capsys.readouterr().err.startswith("error: ")


def test_a_package_that_cannot_even_start_is_taken_back(runtime_folder: Path, data: Path) -> None:
    run([], runtime(runtime_folder, data, Program(data)))
    update(data, "0.7.0")

    class Broken(Program):
        def launch(self, chosen: Package, arguments: list[str]) -> int:
            self.started.append((chosen.version, arguments))
            raise ImportError(chosen.version)

    program = Broken(data, code=4)
    # The previous version starts in its place; its exit code is the program's.
    assert run([], runtime(runtime_folder, data, program)) == 4
    assert load_state(data).failed == ["0.7.0"]
    assert program.restarts == 1


def test_the_setup_starts_the_boot() -> None:
    entry = importlib.import_module("rhinvoice_boot.__main__")
    assert entry.main is boot.main


def test_a_second_start_only_shows_the_running_program(runtime_folder: Path, data: Path) -> None:
    program = Program(data)
    with session(data) as first:
        assert first
        # Another process: the environment of this one says it holds the session.
        os.environ.pop(SESSION)
        try:
            run(["--no-browser"], runtime(runtime_folder, data, program))
        finally:
            os.environ[SESSION] = "1"
    [(_version, arguments)] = program.started
    assert arguments[-1] == "--attach"
    assert load_state(data) == State()  # nothing changed by the second start


def test_a_restarted_boot_runs_in_its_parents_session(data: Path) -> None:
    with session(data) as first, session(data) as child:
        assert first
        assert child


def test_a_database_that_could_not_be_put_back_is_put_back_at_the_next_start(
    runtime_folder: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed(runtime_folder, data)
    update(data, "0.7.0")
    monkeypatch.setattr(boot, "RETRY_PAUSE_SECONDS", 0)
    real_copytree = shutil.copytree
    calls = 0

    def copy_once_then_fail(source: Path, target: Path) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return real_copytree(source, target)

    monkeypatch.setattr(shutil, "copytree", copy_once_then_fail)

    class Migrating(Program):
        def launch(self, chosen: Package, arguments: list[str]) -> int:
            (self.data / "database" / "invoices").write_text("half migrated")
            return super().launch(chosen, arguments)

    with pytest.raises(BootError, match="could not be put back"):
        run([], runtime(runtime_folder, data, Migrating(data, works=False, code=1)))
    assert load_state(data) == State(active="0.6.2", failed=["0.7.0"], restore="0.7.0")
    # The next start puts the database back before anything runs.
    program = Program(data)
    run([], runtime(runtime_folder, data, program))
    assert (data / "database" / "invoices").read_text() == "before the update"
    assert [version for version, _ in program.started] == ["0.6.2"]
    assert load_state(data) == State(active="0.6.2", failed=["0.7.0"])


def test_a_file_that_windows_keeps_locked_for_a_moment_is_tried_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(boot, "RETRY_PAUSE_SECONDS", 0)
    attempts: list[int] = []

    def locked_twice() -> None:
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError("used by another process")

    def locked() -> None:
        raise PermissionError("used by another process")

    boot.retry(locked_twice)
    assert len(attempts) == 3
    with pytest.raises(PermissionError):
        boot.retry(locked, attempts=2)


def test_without_a_copy_of_the_database_the_previous_version_starts(
    runtime_folder: Path,
    data: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installed(runtime_folder, data)
    update(data, "0.7.0")

    def disk_full(_source: Path, _target: Path) -> object:
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copytree", disk_full)
    program = Program(data)
    run([], runtime(runtime_folder, data, program))
    assert [version for version, _ in program.started] == ["0.6.2"]
    assert "no copy of the database before 0.7.0: disk full" in capsys.readouterr().err
    assert load_state(data) == State(active="0.6.2")


def test_without_a_copy_and_without_the_previous_package_nothing_starts(
    runtime_folder: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed(runtime_folder, data)
    save_state(data, State(active="0.5.0"))  # its package was removed
    update(data, "0.7.0")

    def disk_full(_source: Path, _target: Path) -> object:
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copytree", disk_full)
    with raises_exactly(BootError, "the version that ran before (0.5.0) is no longer installed"):
        run([], runtime(runtime_folder, data, Program(data)))


def test_confirming_keeps_the_last_three_versions_and_copies(data: Path) -> None:
    for version in ("0.6.0", "0.6.1", "0.6.2", "0.7.0", "0.10.0"):
        update(data, version)
        (data / "backups" / f"database-before-{version}").mkdir(parents=True)
        (data / "backups" / f"database-failed-{version}").mkdir(parents=True)
    (data / "app" / "versions" / "0.11.0.partial").mkdir()  # a download in progress
    save_state(data, State(active="0.7.0", trying="0.10.0", saved=True))
    confirm(data)
    versions = sorted(f.name for f in (data / "app" / "versions").iterdir())
    assert versions == ["0.10.0", "0.11.0.partial", "0.6.1", "0.6.2", "0.7.0"]
    copies = sorted(f.name for f in (data / "backups").iterdir())
    assert copies == [
        "database-before-0.10.0", "database-before-0.6.2", "database-before-0.7.0",
        "database-failed-0.10.0", "database-failed-0.6.2", "database-failed-0.7.0",
    ]  # fmt: skip


def test_pruning_without_updates_or_copies_does_nothing(data: Path) -> None:
    prune(data, "0.6.2")
    assert not data.exists()


def test_without_a_console_the_boot_writes_to_a_file(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    log_without_console(data)
    log = sys.stderr
    assert log is not None
    assert log is sys.stdout
    log.write("error: x\n")
    log.close()
    assert (data / "rhinvoice.log").read_text() == "error: x\n"


def test_with_a_console_the_messages_stay_there(data: Path) -> None:
    log_without_console(data)
    assert not (data / "rhinvoice.log").exists()


def test_the_interface_of_the_boot_for_app_packages_stays_as_it_is() -> None:
    """App packages use the runtime's boot (ADR 0022): renaming any of this needs a new setup."""
    for name in (
        "confirm",
        "BootError",
        "data_folder",
        "runtime_generation",
        "load_state",
        "make_private",
        "log_without_console",
    ):
        assert callable(getattr(boot, name)), name
    assert RESTART == 75
    assert {"failed"} <= set(State.__dataclass_fields__)
    arguments = ["--install-dir", "/i", "--static-dir", "/s", "--data-dir", "/d", "--attach"]
    parsed = launcher_parser().parse_args(arguments)
    assert (parsed.install_dir, parsed.static_dir, parsed.data_dir, parsed.attach) == (
        Path("/i"),
        Path("/s"),
        Path("/d"),
        True,
    )


def test_the_tests_leave_the_bytecode_settings_of_this_process_alone() -> None:
    """Runs after the tests of main() (pytest keeps the order of a module)."""
    assert os.environ.get("PYTHONPYCACHEPREFIX") == PREFIX_BEFORE
