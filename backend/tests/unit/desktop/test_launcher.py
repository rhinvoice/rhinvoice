"""rhinvoice-desktop: database, settings, browser and server put together."""

import importlib
import json
import socket
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from rhinvoice.api.settings import Settings
from rhinvoice.desktop import launcher
from rhinvoice.desktop.launcher import Desktop, build_parser, run, wait_until_answers, when_ready
from rhinvoice.desktop.ports import free_port
from rhinvoice.desktop.postgres import BundledPostgres
from rhinvoice_boot import State, load_state, save_state
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


def ignore_page(_address: str, _folder: Path, _open_page: object = None) -> bool:
    """Open nothing."""
    return True


def never(_address: str) -> bool:
    return False


def always(_address: str) -> bool:
    return True


def desktop(install: Path, tmp_path: Path, recorder: Recorder) -> Desktop:
    return Desktop(
        serve=recorder.serve,
        open_page=lambda _address: None,
        show_window=None,
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


def test_a_port_in_use_is_left_to_its_program(install: Path, tmp_path: Path, data: Path) -> None:
    taken = port_of(data)
    recorder = Recorder()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", taken))
        listener.listen()
        assert (
            run(build_parser().parse_args(["--no-browser"]), desktop(install, tmp_path, recorder))
            == 0
        )
    [(_settings, _host, port)] = recorder.calls
    # Another port, kept for the next starts (bookmarks stay valid from then on).
    assert port != taken
    assert port_of(data) == port


def test_a_second_start_shows_the_running_one(
    install: Path, tmp_path: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    recorder = Recorder()
    surroundings = replace(desktop(install, tmp_path, recorder), open_page=opened.append)
    args = build_parser().parse_args(["--browser"])
    monkeypatch.setattr(launcher, "when_ready", ignore_page)

    def serve_and_start_again(settings: Settings, host: str, port: int) -> int:
        recorder.calls.append((settings, host, port))

        # While the first one runs, the user starts the program again.
        def answers(address: str) -> bool:
            return address.endswith(f":{port}")

        monkeypatch.setattr(launcher, "answers", answers)
        assert run(args, replace(surroundings, serve=recorder.serve)) == 0
        return 0

    assert run(args, replace(surroundings, serve=serve_and_start_again)) == 0
    assert len(recorder.calls) == 1
    assert opened == [f"http://127.0.0.1:{port_of(data)}"]


def test_a_database_left_by_a_killed_program_is_not_taken_for_a_running_one(
    install: Path, tmp_path: Path, data: Path
) -> None:
    # The program was killed: its database still runs, but nothing answers on its port.
    BundledPostgres(install / "postgresql" / "bin", data / "database", "secret", 5432).start()
    recorder = Recorder()
    args = build_parser().parse_args(["--no-browser"])
    assert run(args, desktop(install, tmp_path, recorder)) == 0
    assert len(recorder.calls) == 1


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

    def when_ready(address: str, _folder: Path, open_page: object = None) -> bool:
        opened.append((address, open_page))
        return True

    monkeypatch.setattr(launcher, "when_ready", when_ready)
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


def test_once_the_server_answers_the_version_is_confirmed_and_opened(
    health: str, tmp_path: Path
) -> None:
    # An update that still has to prove itself.
    save_state(tmp_path, State(active="0.6.2", trying="0.7.0", saved=True))
    opened: list[str] = []
    assert when_ready(health, tmp_path, opened.append)
    assert opened == [health]
    assert load_state(tmp_path) == State(active="0.7.0")


def test_a_server_that_never_answers_is_not_waited_for_forever() -> None:
    assert not wait_until_answers(f"http://127.0.0.1:{free_port()}", timeout=0.6)


def test_a_database_in_an_unknown_state_stops_the_program(
    install: Path,
    tmp_path: Path,
    data: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    postgres = BundledPostgres(install / "postgresql" / "bin", data / "database", "secret", 5432)
    postgres.start()
    postgres.stop()
    monkeypatch.setenv("FAKE_POSTGRES_STATUS", "4")
    recorder = Recorder()
    assert (
        run(build_parser().parse_args(["--no-browser"]), desktop(install, tmp_path, recorder)) == 1
    )
    assert recorder.calls == []
    assert capsys.readouterr().err == "error: pg_ctl status failed (4): \n"


class Window:
    """Records the windows the program shows, after its server answered."""

    def __init__(self, recorder: Recorder) -> None:
        self.recorder = recorder
        self.shown: list[tuple[str, Path]] = []

    def show(self, address: str, storage: Path) -> None:
        self.shown.append((address, storage))

    def wait(self, _address: str, timeout: float = 5) -> bool:
        deadline = time.monotonic() + timeout
        while not self.recorder.calls and time.monotonic() < deadline:
            time.sleep(0.01)
        return bool(self.recorder.calls)


def test_the_interface_opens_in_a_window_beside_the_server(
    install: Path, tmp_path: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    window = Window(recorder)
    monkeypatch.setattr(launcher, "wait_until_answers", window.wait)
    surroundings = replace(desktop(install, tmp_path, recorder), show_window=window.show)
    assert run(build_parser().parse_args([]), surroundings) == 0
    assert len(recorder.calls) == 1
    assert window.shown == [(f"http://127.0.0.1:{port_of(data)}", data / "window")]
    # Closing the window ends the program: the database is stopped.
    assert commands(tmp_path)[-1] == "pg_ctl stop"


def test_a_server_that_does_not_answer_shows_no_window(
    install: Path,
    tmp_path: Path,
    data: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    window = Window(Recorder())
    monkeypatch.setattr(launcher, "wait_until_answers", never)
    surroundings = replace(desktop(install, tmp_path, Recorder()), show_window=window.show)
    assert run(build_parser().parse_args([]), surroundings) == 1
    assert window.shown == []
    address = f"http://127.0.0.1:{port_of(data)}"
    assert capsys.readouterr().err == f"error: the web interface did not start on {address}\n"
    assert commands(tmp_path)[-1] == "pg_ctl stop"


@pytest.mark.usefixtures("data")
def test_the_browser_can_be_chosen_over_the_window(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []

    def when_ready(address: str, _folder: Path, _open_page: object = None) -> bool:
        opened.append(address)
        return True

    monkeypatch.setattr(launcher, "when_ready", when_ready)
    recorder = Recorder()
    window = Window(recorder)
    surroundings = replace(desktop(install, tmp_path, recorder), show_window=window.show)
    assert run(build_parser().parse_args(["--browser"]), surroundings) == 0
    assert window.shown == []
    assert len(opened) == 1


def test_a_second_start_shows_the_running_one_in_a_window(
    install: Path, tmp_path: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    postgres = BundledPostgres(install / "postgresql" / "bin", data / "database", "secret", 5432)
    postgres.start()
    monkeypatch.setattr(launcher, "answers", always)
    recorder = Recorder()
    window = Window(recorder)
    surroundings = replace(desktop(install, tmp_path, recorder), show_window=window.show)
    assert run(build_parser().parse_args([]), surroundings) == 0
    assert recorder.calls == []
    assert window.shown == [(f"http://127.0.0.1:{port_of(data)}", data / "window")]
    # As a server only, a second start shows nothing.
    assert run(build_parser().parse_args(["--no-browser"]), surroundings) == 0
    assert len(window.shown) == 1


def test_without_a_console_messages_go_to_a_file(
    install: Path, tmp_path: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    (data / "rhinvoice.json").write_text("{")
    assert run(build_parser().parse_args([]), desktop(install, tmp_path, Recorder())) == 1
    log = sys.stderr
    assert log is not None
    assert log is sys.stdout
    log.close()  # the program keeps it open until it ends
    assert (data / "rhinvoice.log").read_text().startswith("error: ")


def test_the_installers_start_the_launcher() -> None:
    entry = importlib.import_module("rhinvoice.desktop.__main__")
    assert entry.main is launcher.main
