"""rhinvoice-desktop: database, settings, browser and server put together."""

import importlib
import json
import signal
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from rhinvoice.api.container import NO_OWN_SERVICES, OwnServices
from rhinvoice.api.settings import Settings
from rhinvoice.application.backup.ports import BackupFailed, FolderSuggestion
from rhinvoice.application.updates.ports import PackageFile, Release
from rhinvoice.desktop import launcher
from rhinvoice.desktop import window as program_window
from rhinvoice.desktop.backup import FOLDER_NAME, CurrentArchive, DesktopBackupSetup
from rhinvoice.desktop.edition import BETA, STABLE
from rhinvoice.desktop.launcher import (
    Desktop,
    build_parser,
    program_log,
    run,
    wait_until_answers,
    when_ready,
)
from rhinvoice.desktop.ports import free_port
from rhinvoice.desktop.postgres import BundledPostgres
from rhinvoice.desktop.setup import SetupDownloader
from rhinvoice.desktop.updates import BUILD, VERIFIED, PackageInstaller
from rhinvoice.infrastructure.updates.feed import installed_version
from rhinvoice_boot import RESTART, State, load_state, save_state
from tests.helpers import raises_exactly
from tests.unit.desktop.tools import calls, commands


class Recorder:
    def __init__(self, result: int = 0) -> None:
        self.result = result
        self.calls: list[tuple[Settings, str, int]] = []
        self.owns: list[OwnServices] = []
        self.stops: list[threading.Event | None] = []

    def serve(
        self,
        settings: Settings,
        host: str,
        port: int,
        *,
        own: OwnServices = NO_OWN_SERVICES,
        stop: threading.Event | None = None,
    ) -> int:
        self.calls.append((settings, host, port))
        self.owns.append(own)
        self.stops.append(stop)
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


def never_answers(_address: str, _running: Callable[[], bool]) -> bool:
    return False


def always(_address: str) -> bool:
    return True


def desktop(install: Path, tmp_path: Path, recorder: Recorder) -> Desktop:
    return Desktop(
        serve=recorder.serve,
        open_page=lambda _address: None,
        show_window=None,
        system="Linux",
        machine="x86_64",
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
    assert settings.local_port == port
    assert settings.reset_code_dir == data
    assert settings.log_file == data / "rhinvoice.log"
    assert settings.update_channel == "stable"
    assert settings.update_check
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

    def serve_and_start_again(
        settings: Settings,
        host: str,
        port: int,
        *,
        own: OwnServices = NO_OWN_SERVICES,
        stop: threading.Event | None = None,
    ) -> int:
        del stop, own
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


def test_database_tools_removed_while_it_runs_are_reported(
    install: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A setup run beside the program removed pg_ctl: closing reports it, never crashes."""

    def serve_while_a_setup_runs(
        settings: Settings,
        host: str,
        port: int,
        *,
        own: OwnServices = NO_OWN_SERVICES,
        stop: threading.Event | None = None,
    ) -> int:
        del settings, host, port, own, stop
        (install / "postgresql" / "bin").unlink()
        return 0

    surroundings = replace(desktop(install, tmp_path, Recorder()), serve=serve_while_a_setup_runs)
    assert run(build_parser().parse_args(["--no-browser"]), surroundings) == 0
    assert capsys.readouterr().err.startswith("error: ")


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
    deadline = time.monotonic() + 0.6
    address = f"http://127.0.0.1:{free_port()}"
    assert not wait_until_answers(address, running=lambda: time.monotonic() < deadline)


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

    def wait(self, _address: str, _running: Callable[[], bool]) -> bool:
        deadline = time.monotonic() + 5
        while not self.recorder.calls and time.monotonic() < deadline:
            time.sleep(0.01)
        return bool(self.recorder.calls)


def test_the_interface_opens_in_a_window_beside_the_server(
    install: Path, tmp_path: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    window = Window(recorder)
    monkeypatch.setattr(launcher, "wait_until_answers", window.wait)
    steps: list[str] = []
    surroundings = replace(
        desktop(install, tmp_path, recorder), show_window=window.show, status=steps.append
    )
    assert run(build_parser().parse_args([]), surroundings) == 0
    assert len(recorder.calls) == 1
    assert window.shown == [(f"http://127.0.0.1:{port_of(data)}", data / "window")]
    # The start card follows the start.
    assert steps == ["database", "data", "ready"]
    # Closing the window stops the server, then the database.
    [stop] = recorder.stops
    assert stop is not None
    assert stop.is_set()
    assert commands(tmp_path)[-1] == "pg_ctl stop"


def test_a_server_that_does_not_answer_shows_no_window(
    install: Path,
    tmp_path: Path,
    data: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    window = Window(Recorder())
    monkeypatch.setattr(launcher, "wait_until_answers", never_answers)
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


def test_a_second_start_brings_the_running_window_forward(
    install: Path, tmp_path: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    postgres = BundledPostgres(install / "postgresql" / "bin", data / "database", "secret", 5432)
    postgres.start()
    monkeypatch.setattr(launcher, "answers", always)
    recorder = Recorder()
    window = Window(recorder)
    asked: list[Path] = []
    surroundings = replace(
        desktop(install, tmp_path, recorder), show_window=window.show, bring_forward=asked.append
    )
    assert run(build_parser().parse_args([]), surroundings) == 0
    assert recorder.calls == []
    assert window.shown == []  # no second window
    assert asked == [data / "window"]
    # As a server only, a second start shows nothing.
    assert run(build_parser().parse_args(["--no-browser"]), surroundings) == 0
    assert len(asked) == 1


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


@pytest.mark.usefixtures("data")
def test_started_by_the_boot_it_can_install_updates(install: Path, tmp_path: Path) -> None:
    (install / "runtime.json").write_text('{"generation": 1}')
    recorder = Recorder()
    run(build_parser().parse_args(["--no-browser"]), desktop(install, tmp_path, recorder))
    [own] = recorder.owns
    installer = own.installer
    assert isinstance(installer, PackageInstaller)
    assert (installer.platform, installer.runtime) == ("linux-x64", 1)
    # Only Windows and macOS know how to run a setup (ADR 0031).
    assert own.setup_installer is None


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_on_windows_and_macos_it_can_install_a_new_setup(
    install: Path, tmp_path: Path, system: str
) -> None:
    (install / "runtime.json").write_text('{"generation": 1}')
    recorder = Recorder()
    surroundings = replace(desktop(install, tmp_path, recorder), system=system)
    run(build_parser().parse_args(["--no-browser"]), surroundings)
    [own] = recorder.owns
    assert isinstance(own.setup_installer, SetupDownloader)


@pytest.mark.usefixtures("data")
def test_without_a_runtime_there_is_nothing_to_install_into(install: Path, tmp_path: Path) -> None:
    recorder = Recorder()
    run(build_parser().parse_args(["--no-browser"]), desktop(install, tmp_path, recorder))
    assert recorder.owns == [NO_OWN_SERVICES]


@pytest.mark.usefixtures("data")
def test_after_an_update_the_boot_is_asked_to_start_again(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (install / "runtime.json").write_text('{"generation": 1}')
    stopped = threading.Event()

    def raise_signal(_signal: int) -> None:
        stopped.set()

    monkeypatch.setattr(signal, "raise_signal", raise_signal)

    def serve_and_update(
        settings: Settings,
        host: str,
        port: int,
        *,
        own: OwnServices = NO_OWN_SERVICES,
        stop: threading.Event | None = None,
    ) -> int:
        del stop
        del settings, host, port
        installer = own.installer
        assert installer is not None
        # An update that is already in place: the program only restarts.
        package = PackageFile("https://x/app.zip", "ab" * 32, 1)
        folder = tmp_path / "home" / "rhinvoice" / "app" / "versions" / "0.7.0"
        folder.mkdir(parents=True)
        (folder / VERIFIED).write_text(package.sha256)
        assert isinstance(installer, PackageInstaller)
        installer.install(Release("0.7.0", "https://x", 1, {installer.platform: package}))
        assert stopped.wait(5)  # the server was stopped as by Ctrl+C
        return 0

    surroundings = replace(desktop(install, tmp_path, Recorder()), serve=serve_and_update)
    assert run(build_parser().parse_args(["--no-browser"]), surroundings) == RESTART


def test_in_a_window_an_update_closes_the_window(
    install: Path, tmp_path: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = Recorder()
    window = Window(recorder)
    closed: list[str] = []
    monkeypatch.setattr(launcher, "wait_until_answers", window.wait)
    surroundings = replace(
        desktop(install, tmp_path, recorder),
        show_window=window.show,
        close_window=lambda: closed.append("closed"),
    )
    run(build_parser().parse_args([]), surroundings)
    [own] = recorder.owns
    assert own.installer is None  # no runtime: the window still gets the restart wiring
    assert window.shown == [(f"http://127.0.0.1:{port_of(data)}", data / "window")]


def test_a_second_start_shows_the_first_once_it_answers(
    install: Path, tmp_path: Path, data: Path, health: str
) -> None:
    port = int(health.rsplit(":", 1)[1])
    (data / "rhinvoice.json").write_text(json.dumps({"database_password": "x", "port": port}))
    opened: list[str] = []
    surroundings = replace(desktop(install, tmp_path, Recorder()), open_page=opened.append)
    assert run(build_parser().parse_args(["--attach"]), surroundings) == 0
    assert opened == [health]
    assert commands(tmp_path) == []  # the database belongs to the first one


def test_a_second_start_asks_the_first_for_its_window_at_once(
    install: Path, tmp_path: Path, data: Path
) -> None:
    """The first one may still migrate: its window comes forward once it shows."""
    asked: list[Path] = []
    surroundings = replace(desktop(install, tmp_path, Recorder()), bring_forward=asked.append)
    assert run(build_parser().parse_args(["--attach"]), surroundings) == 0
    assert asked == [data / "window"]


def test_a_second_start_in_the_browser_opens_the_page(
    install: Path, tmp_path: Path, data: Path, health: str
) -> None:
    port = int(health.rsplit(":", 1)[1])
    (data / "rhinvoice.json").write_text(json.dumps({"database_password": "x", "port": port}))
    opened: list[str] = []
    asked: list[Path] = []
    surroundings = replace(
        desktop(install, tmp_path, Recorder()), open_page=opened.append, bring_forward=asked.append
    )
    assert run(build_parser().parse_args(["--attach", "--browser"]), surroundings) == 0
    assert opened == [health]
    assert asked == []


@pytest.mark.usefixtures("data")
def test_a_first_start_that_never_answers_is_reported(
    install: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(launcher, "ATTACH_SECONDS", 0.3)
    assert run(build_parser().parse_args(["--attach"]), desktop(install, tmp_path, Recorder())) == 1
    assert (
        "Rhinvoice runs already, but does not answer on http://127.0.0.1:"
        in capsys.readouterr().err
    )


class Card:
    """Stands in for the start card of window.run_with_splash."""

    def __init__(self) -> None:
        self.storage: list[Path] = []
        self.titles: list[str] = []

    def show(self, address: str, storage: Path) -> None:
        """Show the program window (not called here)."""

    def status(self, step: str) -> None:
        """Show the step (not called here)."""

    def run_with_splash(
        self, start: Callable[["Card"], int], storage: Path, version: str, title: str
    ) -> int:
        assert version
        self.storage.append(storage)
        self.titles.append(title)
        return start(self)


def test_main_shows_the_start_card_for_a_window(
    install: Path, data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = Card()
    started: list[Desktop] = []

    def run_card(_args: object, surroundings: Desktop) -> int:
        started.append(surroundings)
        return 7

    monkeypatch.setattr(program_window, "available", lambda: True)
    monkeypatch.setattr(program_window, "run_with_splash", card.run_with_splash)
    monkeypatch.setattr(launcher, "run", run_card)
    monkeypatch.setattr(launcher, "end_on_break", lambda: None)
    assert launcher.main(["--data-dir", str(data), "--install-dir", str(install)]) == 7
    assert card.storage == [data / "window"]
    assert card.titles == ["Rhinvoice"]
    [surroundings] = started
    assert surroundings.show_window == card.show
    assert surroundings.status == card.status
    assert surroundings.bring_forward is program_window.ask_to_bring_forward


def ends(_args: object, _desktop: object) -> int:
    return 0


@pytest.mark.parametrize(
    "arguments",
    [["--browser"], ["--no-browser"], ["--attach"], ["--restore", "latest"], ["--list-backups"]],
)
def test_main_shows_no_start_card_without_a_window_of_its_own(
    arguments: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    card = Card()
    monkeypatch.setattr(program_window, "available", lambda: True)
    monkeypatch.setattr(program_window, "run_with_splash", card.run_with_splash)
    monkeypatch.setattr(launcher, "run", ends)
    monkeypatch.setattr(launcher, "end_on_break", lambda: None)
    assert launcher.main(arguments) == 0
    assert card.storage == []


def test_windows_request_to_end_is_handled_like_ctrl_c(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without it Windows ends the process before the program stops its database."""
    monkeypatch.setattr(signal, "SIGBREAK", signal.SIGUSR1, raising=False)
    before = signal.getsignal(signal.SIGUSR1)
    try:
        launcher.end_on_break()
        assert signal.getsignal(signal.SIGUSR1) is signal.default_int_handler
    finally:
        signal.signal(signal.SIGUSR1, before)
    monkeypatch.delattr(signal, "SIGBREAK")
    launcher.end_on_break()  # elsewhere there is nothing to do


def test_asked_to_end_the_program_ends_without_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(_args: object, _desktop: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(launcher, "run", interrupted)
    monkeypatch.setattr(launcher, "end_on_break", lambda: None)
    assert launcher.main(["--no-browser"]) == 0


def bundled_backups(install: Path, tmp_path: Path, restic: str, content: str) -> OwnServices:
    (install / "restic").mkdir()
    (install / "restic" / restic).write_text(content)
    (install / "restic" / restic).chmod(0o755)
    recorder = Recorder()
    run(build_parser().parse_args(["--no-browser"]), desktop(install, tmp_path, recorder))
    [own] = recorder.owns
    return own


@pytest.mark.usefixtures("data")
def test_with_a_bundled_restic_the_program_backs_up_itself(install: Path, tmp_path: Path) -> None:
    """ADR 0023: the folder and key are set up on the settings page; Dropbox is suggested."""
    (tmp_path / "Dropbox").mkdir()
    refusing = '#!/bin/sh\necho "Fatal: stand-in" >&2\nexit 1\n'
    own = bundled_backups(install, tmp_path, "restic", refusing)
    setup, archive = own.backup_setup, own.backup_archive
    assert isinstance(setup, DesktopBackupSetup)
    assert isinstance(archive, CurrentArchive)
    target = setup.target()
    assert target.folder is None
    assert target.suggestions == [
        FolderSuggestion("Dropbox", str(tmp_path / "Dropbox" / FOLDER_NAME))
    ]
    with raises_exactly(BackupFailed, "backups are not set up"):
        archive.back_up()
    # The bundled restic opens the folder.
    with raises_exactly(BackupFailed, "Fatal: stand-in"):
        setup.set_up(str(tmp_path / "Dropbox" / FOLDER_NAME))


@pytest.mark.usefixtures("data")
def test_on_windows_restic_is_found_by_its_full_name(install: Path, tmp_path: Path) -> None:
    own = bundled_backups(install, tmp_path, "restic.exe", "")
    assert isinstance(own.backup_setup, DesktopBackupSetup)


@pytest.fixture
def restorable(
    install: Path, data: Path, restic_tool: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Give the installation a restic stand-in and a backup folder set up with a key."""
    (install / "restic").mkdir()
    (install / "restic" / "restic").symlink_to(restic_tool)
    monkeypatch.setenv("FAKE_RESTIC_LOG", str(tmp_path / "restic.jsonl"))
    for name in ("FAKE_RESTIC_FAIL", "FAKE_RESTIC_CAT_CODE", "FAKE_RESTIC_DUMP"):
        monkeypatch.delenv(name, raising=False)
    config = json.loads((data / "rhinvoice.json").read_text())
    backups = tmp_path / "OneDrive" / "Rhinvoice-Backup"
    config |= {"backup_folder": str(backups), "backup_key": "K7QM-2XWP"}
    (data / "rhinvoice.json").write_text(json.dumps(config))
    return backups


def restic_calls(tmp_path: Path) -> list[dict[str, object]]:
    lines = (tmp_path / "restic.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def no_secret(prompt: str) -> str:
    msg = f"asked for {prompt!r}"
    raise AssertionError(msg)


def restore(install: Path, tmp_path: Path, *arguments: str, key: str | None = None) -> int:
    def typed(prompt: str) -> str:
        assert prompt == "Recovery key: "
        assert key is not None
        return key

    asked = no_secret if key is None else typed
    surroundings = replace(desktop(install, tmp_path, Recorder()), ask_secret=asked)
    return run(build_parser().parse_args(list(arguments)), surroundings)


def test_a_backup_replaces_the_data(
    install: Path,
    data: Path,
    restorable: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ADR 0023: the database runs only for the restore; the server does not start."""
    assert restore(install, tmp_path, "--restore", "latest") == 0
    [dump] = restic_calls(tmp_path)
    assert dump["arguments"] == ["dump", "--tag", "rhinvoice", "latest", "/rhinvoice.sql"]
    assert (dump["password"], dump["repository"]) == ("K7QM-2XWP", str(restorable))
    # A fresh database first (initdb, createdb), then the restore in one psql call.
    assert commands(tmp_path)[-4:] == ["createdb", "psql", "pg_ctl status", "pg_ctl stop"]
    assert "--single-transaction" in calls(tmp_path)[-3].arguments
    assert capsys.readouterr().out.endswith(
        f"Restored latest from {restorable}; start Rhinvoice again.\n"
    )
    assert json.loads((data / "rhinvoice.json").read_text())["backup_key_confirmed"] is True


def test_on_a_new_computer_the_folder_is_named_and_the_key_typed(
    install: Path, data: Path, restorable: Path, tmp_path: Path
) -> None:
    (data / "rhinvoice.json").write_text(json.dumps({"database_password": "secret"}))
    arguments = ("--restore", "4f3a9c1e", "--backup-folder", str(restorable))
    assert restore(install, tmp_path, *arguments, key=" K7QM-2XWP \n") == 0
    assert restic_calls(tmp_path)[0]["password"] == "K7QM-2XWP"
    # Backups go on into the same folder.
    config = json.loads((data / "rhinvoice.json").read_text())
    assert (config["backup_folder"], config["backup_key"]) == (str(restorable), "K7QM-2XWP")


def test_the_backups_are_listed_without_starting_the_database(
    install: Path, restorable: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del restorable
    assert restore(install, tmp_path, "--list-backups") == 0
    assert "4f3a9c1e  2026-03-09 09:00:00" in capsys.readouterr().out
    assert "pg_ctl start" not in commands(tmp_path)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--restore", "latest", "--attach"], "Rhinvoice runs: quit it first"),
        (
            ["--restore", "latest", "--backup-folder", "/elsewhere"],
            "Fatal: wrong password or no key found",
        ),
    ],
)
def test_a_restore_is_refused(
    install: Path,
    restorable: Path,
    tmp_path: Path,
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    message: str,
) -> None:
    del restorable
    monkeypatch.setenv("FAKE_RESTIC_FAIL", "dump")
    monkeypatch.setenv("FAKE_RESTIC_ERROR", "Fatal: wrong password or no key found")
    assert restore(install, tmp_path, *arguments, key="WRONG") == 1
    assert capsys.readouterr().err == f"error: {message}\n"


def test_a_failed_restore_stops_the_database(
    install: Path, restorable: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del restorable
    monkeypatch.setenv("FAKE_RESTIC_DUMP", "CREATE TABLE public.documents (\n")
    assert restore(install, tmp_path, "--restore", "latest") == 1
    assert commands(tmp_path)[-1] == "pg_ctl stop"
    # Only the check for the database ran; nothing was replaced.
    [check] = [call for call in calls(tmp_path) if call.command == "psql"]
    assert "--list" in check.arguments


@pytest.mark.usefixtures("data")
def test_without_a_backup_folder_or_restic_there_is_nothing_to_restore(
    install: Path, tmp_path: Path, restic_tool: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert restore(install, tmp_path, "--restore", "latest") == 1
    assert capsys.readouterr().err == "error: this installation has no restic to restore with\n"
    (install / "restic").mkdir()
    (install / "restic" / "restic").symlink_to(restic_tool)
    assert restore(install, tmp_path, "--list-backups") == 1
    assert capsys.readouterr().err == (
        "error: name the folder of the backups: --backup-folder <folder>\n"
    )


def test_a_running_program_is_not_restored_under_its_feet(
    install: Path, restorable: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del restorable

    def running(_database: BundledPostgres, _port: int) -> bool:
        return True

    monkeypatch.setattr(launcher, "_already_running", running)
    assert restore(install, tmp_path, "--restore", "latest") == 1
    assert not (tmp_path / "restic.jsonl").exists()


def test_the_backup_folder_of_a_restore_is_kept_as_a_full_path(
    install: Path,
    data: Path,
    restorable: Path,
    tmp_path: Path,
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Backups go on into it: a relative path would point elsewhere at the next start."""
    (data / "rhinvoice.json").write_text(json.dumps({"database_password": "secret"}))
    arguments = ("--restore", "latest", "--backup-folder", "Rhinvoice-Backup")
    assert restore(install, tmp_path, *arguments, key="K7QM-2XWP") == 1
    assert capsys.readouterr().err == "error: give the full path of the backup folder\n"
    monkeypatch.setenv("HOME", str(tmp_path))
    home = f"~/{restorable.relative_to(tmp_path)}/../Rhinvoice-Backup"
    assert restore(install, tmp_path, "--restore", "latest", "--backup-folder", home, key="K") == 0
    saved = json.loads((data / "rhinvoice.json").read_text())["backup_folder"]
    assert saved == str(restorable.resolve())


def test_a_mac_keeps_its_log_where_console_app_finds_it(tmp_path: Path) -> None:
    folder = tmp_path / "data"
    assert program_log("Darwin", tmp_path, folder, STABLE) == (
        tmp_path / "Library" / "Logs" / "Rhinvoice" / "rhinvoice.log"
    )
    assert program_log("Darwin", tmp_path, folder, BETA) == (
        tmp_path / "Library" / "Logs" / "Rhinvoice Beta" / "rhinvoice.log"
    )
    assert program_log("Windows", tmp_path, folder, BETA) == folder / "rhinvoice.log"


def test_the_update_check_can_be_switched_off_in_the_configuration(
    install: Path, tmp_path: Path, data: Path
) -> None:
    config = json.loads((data / "rhinvoice.json").read_text())
    (data / "rhinvoice.json").write_text(json.dumps(config | {"update_check": False}))
    recorder = Recorder()
    assert (
        run(build_parser().parse_args(["--no-browser"]), desktop(install, tmp_path, recorder)) == 0
    )
    [(settings, _host, _port)] = recorder.calls
    assert settings.update_check is False


def test_rhinvoice_is_never_offered_release_candidates(
    install: Path, tmp_path: Path, data: Path
) -> None:
    """ADR 0030: candidates go to Rhinvoice Beta; "update_channel" in the file is not read."""
    (install / "runtime.json").write_text('{"generation": 1}')
    config = json.loads((data / "rhinvoice.json").read_text())
    (data / "rhinvoice.json").write_text(json.dumps(config | {"update_channel": "test"}))
    recorder = Recorder()
    assert (
        run(build_parser().parse_args(["--no-browser"]), desktop(install, tmp_path, recorder)) == 0
    )
    [(settings, _host, _port)] = recorder.calls
    assert settings.update_channel == "stable"
    [own] = recorder.owns
    assert isinstance(own.installer, PackageInstaller)
    assert own.installer.setup == "linux-x64"


def test_rhinvoice_beta_is_a_separate_installation(install: Path, tmp_path: Path) -> None:
    """ADR 0030: its own data, backup folder and setup, and it is offered release candidates."""
    (install / "runtime.json").write_text('{"generation": 1, "edition": "beta"}')
    (install / "restic").mkdir()
    (install / "restic" / "restic").write_text("")
    (tmp_path / "Dropbox").mkdir()
    recorder = Recorder()
    assert (
        run(build_parser().parse_args(["--no-browser"]), desktop(install, tmp_path, recorder)) == 0
    )
    [(settings, _host, _port)] = recorder.calls
    beta = tmp_path / "home" / "rhinvoice-beta"
    assert settings.reset_code_dir == beta
    assert (beta / "rhinvoice.json").exists()
    assert not (tmp_path / "home" / "rhinvoice").exists()
    assert settings.update_channel == "test"
    [own] = recorder.owns
    assert isinstance(own.installer, PackageInstaller)
    assert (own.installer.platform, own.installer.setup) == ("linux-x64", "linux-x64-beta")
    # Its boot did not say which build runs: no candidates of one version (ADR 0035).
    assert own.installer.candidate is None
    assert isinstance(own.backup_setup, DesktopBackupSetup)
    assert own.backup_setup.target().suggestions == [
        FolderSuggestion("Dropbox", str(tmp_path / "Dropbox" / "Rhinvoice-Beta-Backup"))
    ]


@pytest.mark.parametrize(
    ("runtime", "build", "candidate"),
    [
        ('{"generation": 1, "edition": "beta"}', f"{installed_version()}-rc.3", 3),
        # Rhinvoice is never offered candidates of its version.
        ('{"generation": 1}', f"{installed_version()}-rc.3", None),
        ('{"generation": 1, "edition": "beta"}', installed_version(), None),
    ],
)
def test_rhinvoice_beta_knows_the_candidate_its_boot_started(
    install: Path, tmp_path: Path, runtime: str, build: str, candidate: int | None
) -> None:
    """ADR 0035: the boot names the build it started, and keeps candidates apart."""
    (install / "runtime.json").write_text(runtime)
    recorder = Recorder()
    started = desktop(install, tmp_path, recorder)
    started = replace(started, environ={**started.environ, BUILD: build})
    assert run(build_parser().parse_args(["--no-browser"]), started) == 0
    [own] = recorder.owns
    assert isinstance(own.installer, PackageInstaller)
    assert own.installer.candidate == candidate
