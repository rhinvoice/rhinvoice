"""The boot of the runtime: which app package starts, and how a failed update is taken back."""

import importlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

import rhinvoice_boot as boot
from rhinvoice.desktop.postgres import BundledPostgres
from rhinvoice_boot import (
    RESTART,
    BootError,
    Package,
    Runtime,
    State,
    choose,
    confirm,
    load_state,
    option,
    packages,
    run,
    save_state,
    switch_to,
    version_key,
    without_option,
)
from tests.helpers import raises_exactly
from tests.unit.desktop.tools import commands


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

    def restart(self) -> None:
        self.restarts += 1


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
    # The active one wins, unless it failed.
    assert choose(runtime_folder, data, State(active="0.6.2")).version == "0.6.2"
    assert choose(runtime_folder, data, State(active="0.7.0", failed=["0.7.0"])).version == "0.6.2"


def test_without_a_fitting_package_nothing_starts(runtime_folder: Path, data: Path) -> None:
    with raises_exactly(BootError, f"no app package fits the runtime in {runtime_folder}"):
        choose(runtime_folder, data, State(failed=["0.6.2"]))


def test_a_runtime_without_its_description_asks_for_the_setup(install: Path, data: Path) -> None:
    path = install / "runtime.json"
    with raises_exactly(BootError, f"{path} is missing or damaged: the setup has to be run again"):
        packages(install, data)


@pytest.mark.parametrize(
    "content",
    [
        "{",
        "[]",
        '{"active": 1}',
        '{"previous": 1}',
        '{"pending": "yes"}',
        '{"saved": "yes"}',
        '{"failed": "0.7.0"}',
    ],
)
def test_a_damaged_state_starts_the_newest_package(data: Path, content: str) -> None:
    (data / "app").mkdir(parents=True)
    (data / "app" / "state.json").write_text(content)
    assert load_state(data) == State()


def test_the_state_is_kept_between_starts(data: Path) -> None:
    assert load_state(data) == State()
    state = State(active="0.7.0", previous="0.6.2", pending=True, saved=True, failed=["0.6.9"])
    save_state(data, state)
    assert load_state(data) == state


def test_an_update_has_to_prove_itself_once(data: Path) -> None:
    save_state(data, State(active="0.6.2"))
    switch_to(data, "0.7.0")
    assert load_state(data) == State(active="0.7.0", previous="0.6.2", pending=True)
    confirm(data)
    assert load_state(data) == State(active="0.7.0", previous="0.6.2")
    confirm(data)  # nothing left to confirm
    assert load_state(data) == State(active="0.7.0", previous="0.6.2")


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


def test_the_program_may_ask_to_be_started_again(runtime_folder: Path, data: Path) -> None:
    program = Program(data, code=RESTART)
    assert run([], runtime(runtime_folder, data, program)) == RESTART
    assert program.restarts == 1


def database(install: Path, data: Path) -> BundledPostgres:
    return BundledPostgres(install / "postgresql" / "bin", data / "database", "secret", 5432)


def test_an_update_that_works_keeps_a_copy_of_the_database_from_before(
    runtime_folder: Path, data: Path, tmp_path: Path
) -> None:
    postgres = database(runtime_folder, data)
    postgres.start()  # left running by the version that downloaded the update
    (data / "database" / "invoices").write_text("before the update")
    update(data, "0.7.0")
    save_state(data, State(active="0.6.2"))
    switch_to(data, "0.7.0")
    program = Program(data)
    assert run([], runtime(runtime_folder, data, program)) == 0
    assert [version for version, _ in program.started] == ["0.7.0"]
    copy = data / "backups" / "database-before-0.7.0"
    assert (copy / "invoices").read_text() == "before the update"
    # The copy is taken of the stopped database.
    assert commands(tmp_path)[-2:] == ["pg_ctl status", "pg_ctl stop"]
    assert load_state(data) == State(active="0.7.0", previous="0.6.2", saved=True)


def test_an_update_that_fails_is_taken_back_with_its_database(
    runtime_folder: Path, data: Path
) -> None:
    database(runtime_folder, data).start()
    database(runtime_folder, data).stop()
    (data / "database" / "invoices").write_text("before the update")
    update(data, "0.7.0")
    save_state(data, State(active="0.6.2"))
    switch_to(data, "0.7.0")

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


def test_an_update_without_a_database_yet_is_taken_back_without_one(
    runtime_folder: Path, data: Path
) -> None:
    update(data, "0.7.0")
    switch_to(data, "0.7.0")
    program = Program(data, works=False, code=1)
    assert run([], runtime(runtime_folder, data, program)) == 1
    assert not (data / "database").exists()
    assert load_state(data) == State(active=None, failed=["0.7.0"])


def test_a_failed_update_whose_database_vanished_gets_the_copy_back(
    runtime_folder: Path, data: Path
) -> None:
    database(runtime_folder, data).start()
    database(runtime_folder, data).stop()
    update(data, "0.7.0")
    switch_to(data, "0.7.0")

    class Deleting(Program):
        def launch(self, chosen: Package, arguments: list[str]) -> int:
            shutil.rmtree(self.data / "database")
            return super().launch(chosen, arguments)

    run([], runtime(runtime_folder, data, Deleting(data, works=False, code=1)))
    assert (data / "database" / "PG_VERSION").exists()


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


def test_a_restart_replaces_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def execv(path: str, arguments: list[str]) -> None:
        calls.append((path, arguments))

    monkeypatch.setattr(os, "execv", execv)
    monkeypatch.setattr(sys, "argv", ["rhinvoice_boot", "--browser"])
    boot.restart()
    assert calls == [(sys.executable, [sys.executable, "-m", "rhinvoice_boot", "--browser"])]


def test_options_are_read_in_both_spellings() -> None:
    assert option(["--data-dir", "/d"], "--data-dir") == "/d"
    assert option(["--data-dir=/d"], "--data-dir") == "/d"
    assert option(["--data-dir"], "--data-dir") is None
    assert option([], "--data-dir") is None
    assert without_option(["--data-dir", "/d", "--browser"], "--data-dir") == ["--browser"]
    assert without_option(["--browser", "--data-dir=/d"], "--data-dir") == ["--browser"]


def test_main_starts_from_the_interpreter_of_the_runtime(
    runtime_folder: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = Program(data)
    monkeypatch.setattr(sys, "prefix", str(runtime_folder / "python"))
    monkeypatch.setattr(boot, "launch", program.launch)
    assert boot.main(["--data-dir", str(data), "--no-browser"]) == 0
    [(_version, arguments)] = program.started
    assert arguments[:3] == ["--no-browser", "--install-dir", str(runtime_folder)]


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
    update(data, "0.7.0")
    switch_to(data, "0.7.0")

    class Broken(Program):
        def launch(self, chosen: Package, arguments: list[str]) -> int:
            self.started.append((chosen.version, arguments))
            raise ImportError(chosen.version)

    program = Broken(data)
    assert run([], runtime(runtime_folder, data, program)) == 1
    assert load_state(data).failed == ["0.7.0"]
    assert program.restarts == 1


def test_the_setup_starts_the_boot() -> None:
    entry = importlib.import_module("rhinvoice_boot.__main__")
    assert entry.main is boot.main
