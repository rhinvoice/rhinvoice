"""rhinvoice-desktop: database, settings, browser and server put together."""

import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from rhinvoice.api.settings import Settings
from rhinvoice.desktop import launcher
from rhinvoice.desktop.launcher import Desktop, build_parser, open_when_ready, run
from rhinvoice.desktop.ports import free_port
from tests.unit.desktop.tools import commands


class Recorder:
    def __init__(self, result: int = 0) -> None:
        self.result = result
        self.calls: list[tuple[Settings, str, int]] = []

    def serve(self, settings: Settings, host: str, port: int) -> int:
        self.calls.append((settings, host, port))
        return self.result


@pytest.fixture
def data(tmp_path: Path) -> Path:
    """Make the default data folder with a configuration on a free port.

    Port 8000 may be taken on the test machine (by a Docker Rhinvoice, for example).
    """
    folder = tmp_path / "home" / "rhinvoice"
    folder.mkdir(parents=True)
    config = {"database_password": "secret", "port": free_port()}
    (folder / "rhinvoice.json").write_text(json.dumps(config))
    return folder


def port_of(data: Path) -> int:
    port: int = json.loads((data / "rhinvoice.json").read_text())["port"]
    return port


def desktop(install: Path, tmp_path: Path, recorder: Recorder) -> Desktop:
    return Desktop(
        serve=recorder.serve,
        open_page=lambda _address: None,
        system="Linux",
        environ={"XDG_DATA_HOME": str(tmp_path / "home")},
        home=tmp_path,
        install=install,
    )


def test_the_server_runs_on_the_bundled_database(install: Path, tmp_path: Path, data: Path) -> None:
    (install / "chromium").mkdir()
    (install / "chromium" / "chrome-headless-shell").write_text("")
    recorder = Recorder()
    args = build_parser().parse_args(["--no-browser"])
    assert run(args, desktop(install, tmp_path, recorder)) == 0
    [(settings, host, port)] = recorder.calls
    assert (host, port) == ("127.0.0.1", port_of(data))
    assert settings.database_url.startswith("postgresql+psycopg://rhinvoice:secret@127.0.0.1:")
    assert settings.static_dir == install / "static"
    assert settings.chromium_path == install / "chromium" / "chrome-headless-shell"
    assert not settings.cookie_secure
    assert (data / "database" / "PG_VERSION").exists()
    # The database is stopped with the server.
    assert commands(tmp_path)[-1] == "pg_ctl stop"


def test_folders_given_on_the_command_line_win(install: Path, tmp_path: Path) -> None:
    recorder = Recorder(result=3)
    data = tmp_path / "data"
    data.mkdir()
    (data / "rhinvoice.json").write_text(
        json.dumps({"database_password": "x", "port": free_port()})
    )
    args = build_parser().parse_args(
        ["--no-browser", "--data-dir", str(data), "--install-dir", str(install)]
    )
    assert run(args, desktop(tmp_path / "elsewhere", tmp_path, recorder)) == 3
    assert (data / "database" / "PG_VERSION").exists()


def test_a_port_in_use_stops_the_program_before_the_database_starts(
    install: Path, tmp_path: Path, data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", port_of(data)))
        listener.listen()
        assert run(build_parser().parse_args([]), desktop(install, tmp_path, Recorder())) == 1
    assert capsys.readouterr().err.startswith(f"error: port {port_of(data)} is in use")
    assert commands(tmp_path) == []


def test_a_damaged_configuration_stops_the_program(
    install: Path, tmp_path: Path, data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (data / "rhinvoice.json").write_text("{")
    assert run(build_parser().parse_args([]), desktop(install, tmp_path, Recorder())) == 1
    assert capsys.readouterr().err.startswith("error: ")
    assert commands(tmp_path) == []


@pytest.mark.usefixtures("data")
@pytest.mark.parametrize(
    ("environ", "stopped"),
    [
        # The server did not start: nothing to stop.
        ({"FAKE_POSTGRES_FAIL": "pg_ctl start"}, False),
        # It started, then a step failed: it is stopped again.
        ({"FAKE_POSTGRES_FAIL": "createdb"}, True),
        ({"RHINVOICE_RECURRING_INTERVAL": "1"}, True),  # below the minimum
    ],
)
def test_failures_after_the_database_started_stop_it(
    install: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environ: dict[str, str],
    stopped: bool,
) -> None:
    for name, value in environ.items():
        monkeypatch.setenv(name, value)
    recorder = Recorder()
    assert run(build_parser().parse_args([]), desktop(install, tmp_path, recorder)) == 1
    assert recorder.calls == []
    assert (commands(tmp_path)[-1] == "pg_ctl stop") == stopped


@pytest.mark.usefixtures("data")
def test_a_database_that_does_not_stop_is_reported(
    install: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FAKE_POSTGRES_FAIL", "pg_ctl stop")
    args = build_parser().parse_args(["--no-browser"])
    assert run(args, desktop(install, tmp_path, Recorder())) == 0
    assert capsys.readouterr().err == "error: pg_ctl stop failed (1): boom\n"


def test_the_browser_opens_the_interface(
    install: Path, tmp_path: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[tuple[str, object]] = []

    def open_when_ready(address: str, open_page: object) -> None:
        opened.append((address, open_page))

    monkeypatch.setattr(launcher, "open_when_ready", open_when_ready)
    surroundings = desktop(install, tmp_path, Recorder())
    run(build_parser().parse_args([]), surroundings)
    assert opened == [(f"http://127.0.0.1:{port_of(data)}", surroundings.open_page)]


def test_main_uses_this_computer(
    install: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    monkeypatch.setattr(launcher, "serve", recorder.serve)
    arguments = ["--no-browser", "--data-dir", str(data), "--install-dir", str(install)]
    assert launcher.main(arguments) == 0
    assert len(recorder.calls) == 1


class Health(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200 if self.path == "/api/health" else 404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - the base's name
        """Keep the test output quiet."""


@pytest.fixture
def health() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_the_page_opens_once_the_server_answers(health: str) -> None:
    opened: list[str] = []
    assert open_when_ready(health, opened.append, timeout=5)
    assert opened == [health]


def test_a_server_that_never_answers_opens_nothing() -> None:
    opened: list[str] = []
    assert not open_when_ready(f"http://127.0.0.1:{free_port()}", opened.append, timeout=0.6)
    assert opened == []
