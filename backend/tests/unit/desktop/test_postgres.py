"""The bundled PostgreSQL, against stand-ins for its tools (tests/fake_postgres.py)."""

import stat
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from rhinvoice.desktop.postgres import SERVER_SETTINGS, BundledPostgres, PostgresError
from rhinvoice_boot import NO_WINDOW
from tests.helpers import raises_exactly
from tests.unit.desktop.tools import calls, commands

if TYPE_CHECKING:
    from collections.abc import Callable

PASSWORD = "secret/with:odd@characters"


def database(install: Path, tmp_path: Path, port: int = 54321) -> BundledPostgres:
    return BundledPostgres(
        install / "postgresql" / "bin", tmp_path / "data" / "database", PASSWORD, port
    )


def test_the_first_start_creates_server_and_database(install: Path, tmp_path: Path) -> None:
    postgres = database(install, tmp_path)
    postgres.start()
    assert commands(tmp_path) == ["initdb", "pg_ctl start", "psql", "createdb"]
    initdb, start, psql, createdb = calls(tmp_path)
    data = tmp_path / "data" / "database"
    password_file = initdb.arguments[2]
    assert initdb.arguments == [
        f"--pgdata={data}",
        "--username=rhinvoice",
        password_file,
        "--auth=scram-sha-256",
        "--encoding=UTF8",
        "--no-locale",
    ]
    assert password_file.startswith("--pwfile=")
    # The password file is gone once the server exists.
    assert not Path(password_file.removeprefix("--pwfile=")).exists()
    assert (data / "postgresql.conf").read_text().endswith(SERVER_SETTINGS)
    assert start.arguments == [
        "start",
        "--wait",
        f"--pgdata={data}",
        f"--log={tmp_path / 'data' / 'postgresql.log'}",
        "--options=-p 54321",
    ]
    assert createdb.arguments == [
        "--host=127.0.0.1",
        "--port=54321",
        "--username=rhinvoice",
        "rhinvoice",
    ]
    # Only the clients get the password, not the server that pg_ctl starts.
    assert (initdb.password, start.password) == (None, None)
    assert (psql.password, createdb.password) == (PASSWORD, PASSWORD)
    assert stat.S_IMODE((tmp_path / "data").stat().st_mode) == 0o700
    assert postgres.url == (
        "postgresql+psycopg://rhinvoice:secret%2Fwith%3Aodd%40characters@127.0.0.1:54321/rhinvoice"
    )
    postgres.stop()
    assert commands(tmp_path)[-2:] == ["pg_ctl status", "pg_ctl stop"]
    assert not (data / "postmaster.pid").exists()
    postgres.stop()  # stopped already: nothing to do
    assert commands(tmp_path)[-2:] == ["pg_ctl stop", "pg_ctl status"]


def test_a_server_never_created_is_not_stopped(install: Path, tmp_path: Path) -> None:
    database(install, tmp_path).stop()
    assert commands(tmp_path) == []


def test_later_starts_use_the_existing_database(install: Path, tmp_path: Path) -> None:
    database(install, tmp_path).start()
    database(install, tmp_path).stop()
    first = len(calls(tmp_path))
    database(install, tmp_path, port=54322).start()
    assert commands(tmp_path)[first:] == ["pg_ctl status", "pg_ctl start", "psql"]


def test_a_server_left_running_is_restarted(install: Path, tmp_path: Path) -> None:
    database(install, tmp_path).start()  # never stopped: the program was killed
    first = len(calls(tmp_path))
    database(install, tmp_path).start()
    assert commands(tmp_path)[first:] == ["pg_ctl status", "pg_ctl stop", "pg_ctl start", "psql"]


def test_a_database_missing_after_an_interrupted_first_start_is_created(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_POSTGRES_FAIL", "createdb")
    with pytest.raises(PostgresError):
        database(install, tmp_path).start()
    database(install, tmp_path).stop()
    monkeypatch.delenv("FAKE_POSTGRES_FAIL")
    first = len(calls(tmp_path))
    database(install, tmp_path).start()
    assert commands(tmp_path)[first:] == ["pg_ctl status", "pg_ctl start", "psql", "createdb"]


@pytest.mark.parametrize(
    ("failing", "message"),
    [
        ("initdb", "initdb --pgdata"),
        ("psql", "psql"),
    ],
)
def test_failing_tools_are_reported_with_their_output(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str, message: str
) -> None:
    monkeypatch.setenv("FAKE_POSTGRES_FAIL", failing)
    with pytest.raises(PostgresError, match=f"^{message}.* failed \\(1\\): boom$"):
        database(install, tmp_path).start()


def test_a_server_that_does_not_start_points_to_its_log(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_POSTGRES_FAIL", "pg_ctl start")
    log = tmp_path / "data" / "postgresql.log"
    with raises_exactly(PostgresError, f"pg_ctl start failed (1): see {log}"):
        database(install, tmp_path).start()


def test_an_unknown_server_state_is_reported(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database(install, tmp_path).start()
    monkeypatch.setenv("FAKE_POSTGRES_STATUS", "4")
    with raises_exactly(PostgresError, "pg_ctl status failed (4): "):
        database(install, tmp_path).start()


def test_no_tool_opens_a_console_window(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On Windows every command-line tool would show a black window (Rhinvoice.exe has none)."""
    flags: list[object] = []
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run

    def spy(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:  # noqa: ANN401 - subprocess.run
        flags.append(kwargs.get("creationflags"))
        return run(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    postgres = database(install, tmp_path)
    postgres.start()
    postgres.stop()
    assert flags
    assert set(flags) == {NO_WINDOW}
