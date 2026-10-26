"""The program window and the start card, against a stand-in for pywebview."""

import importlib.util
import json
import platform
import sys
import threading
import time
import types
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import pytest

from rhinvoice.desktop import window
from rhinvoice.desktop.window import Splash, StartSteps

ADDRESS = "http://127.0.0.1:8000"


class Handlers:
    """pywebview's event: handlers are added with +=."""

    def __init__(self) -> None:
        self.added: list[Callable[[], object]] = []

    def __iadd__(self, handler: Callable[[], object]) -> Self:
        self.added.append(handler)
        return self

    def fire(self) -> list[object]:
        return [handler() for handler in self.added]


class Events:
    def __init__(self) -> None:
        self.closing = Handlers()
        self.closed = Handlers()
        self.loaded = Handlers()
        self.maximized = Handlers()
        self.restored = Handlers()


class Created:
    """A window as pywebview makes it: closing may be refused, closed is told."""

    def __init__(self, webview: "FakeWebview", kwargs: dict[str, object]) -> None:
        self.webview = webview
        self.kwargs = kwargs
        self.events = Events()
        self.destroyed = threading.Event()
        self.raised: list[str] = []
        self._on_top = False
        self.geometry: tuple[int, int, int, int] | None = (0, 0, 1280, 860)
        """Where the window is: x, y, width, height; None: macOS lost its screen."""

    def _part(self, index: int) -> int:
        if self.geometry is None:
            msg = "Failed to obtain screen"
            raise RuntimeError(msg)
        return self.geometry[index]

    @property
    def x(self) -> int:
        return self._part(0)

    @property
    def y(self) -> int:
        return self._part(1)

    @property
    def width(self) -> int:
        return self._part(2)

    @property
    def height(self) -> int:
        return self._part(3)

    def destroy(self) -> None:
        if False in self.events.closing.fire():
            return
        self.destroyed.set()
        if self in self.webview.windows:
            self.webview.windows.remove(self)
        self.events.closed.fire()

    def restore(self) -> None:
        self.raised.append("restore")

    def show(self) -> None:
        self.raised.append("show")

    @property
    def on_top(self) -> bool:
        return self._on_top

    @on_top.setter
    def on_top(self, value: bool) -> None:
        self._on_top = value
        self.raised.append(f"on_top={value}")


@dataclass(frozen=True, slots=True)
class Screen:
    x: int
    y: int
    width: int = 1920
    height: int = 1080


MAIN = Screen(0, 0, 2560, 1440)


class FakeWebview(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("webview")
        self.settings: dict[str, object] = {}
        self.created: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.started: list[dict[str, object]] = []
        self.windows: list[Created] = []
        """The open windows, as pywebview lists them."""
        self.without_window = False
        self.on_program_window: Callable[[Created], None] = lambda _window: None
        """What the person does with the program window (in a thread of its own)."""
        self.interrupt = False
        """Ctrl+C reaches the window loop once the program window shows."""
        self.screens = [Screen(-1920, 0), MAIN, Screen(2560, -200)]
        """A screen left of the main one and one to its right, as pywebview lists them."""

    def create_window(self, *args: object, **kwargs: object) -> Created | None:
        self.created.append((args, kwargs))
        created = Created(self, kwargs)
        self.window = created
        # pywebview returns None when it could not make a window.
        if self.without_window:
            return None
        self.windows.append(created)
        if len(args) > 1:  # the program window, with its address
            threading.Thread(target=self.on_program_window, args=(created,)).start()
        return created

    def start(self, func: Callable[[], None] | None = None, **kwargs: object) -> None:
        """Run the window loop: until the last window is closed."""
        self.started.append(kwargs)
        if func is not None:
            func()
        deadline = time.monotonic() + 5
        while self.windows and time.monotonic() < deadline:
            if self.interrupt and len(self.created) > 1:
                raise KeyboardInterrupt
            time.sleep(0.01)


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    # Not macOS: the tests that are say so (cocoa).
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    return fake


class RunLoop:
    """The main thread's NSRunLoop: counts its turns and what happened during them."""

    def __init__(self) -> None:
        self.turns: list[float] = []
        self.during: Callable[[int], None] = lambda _turn: None

    def runUntilDate_(self, date: float) -> None:  # noqa: N802 - pyobjc's name
        self.turns.append(date)
        self.during(len(self.turns))


class Application:
    def __init__(self) -> None:
        self.policies: list[int] = []

    def setActivationPolicy_(self, policy: int) -> None:  # noqa: N802 - pyobjc's name
        self.policies.append(policy)


def in_seconds(seconds: float) -> float:
    """NSDate.dateWithTimeIntervalSinceNow_: the date is told by its distance from now."""
    return seconds


class Cocoa:
    """Stand-ins for pyobjc's Foundation and AppKit, as far as the program uses them."""

    def __init__(self) -> None:
        self.loop = RunLoop()
        self.application = Application()
        self.foundation = types.SimpleNamespace(
            NSRunLoop=types.SimpleNamespace(currentRunLoop=lambda: self.loop),
            NSDate=types.SimpleNamespace(dateWithTimeIntervalSinceNow_=in_seconds),
        )
        self.appkit = types.SimpleNamespace(
            NSApplication=types.SimpleNamespace(sharedApplication=lambda: self.application)
        )


@pytest.fixture
def cocoa(monkeypatch: pytest.MonkeyPatch) -> Cocoa:
    fake = Cocoa()
    monkeypatch.setitem(sys.modules, "Foundation", fake.foundation)
    monkeypatch.setitem(sys.modules, "AppKit", fake.appkit)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    return fake


def handled(shown: Created) -> None:
    """Wait until the program listens to the window (it does so right after making it)."""
    deadline = time.monotonic() + 5
    while not shown.events.closed.added and time.monotonic() < deadline:
        time.sleep(0.01)


def loads_and_closes(shown: Created) -> None:
    """Load the interface, then close the window as the person would."""
    handled(shown)
    shown.events.loaded.fire()
    shown.destroy()


def test_the_start_card_gives_way_to_the_program_window(
    tmp_path: Path, webview: FakeWebview
) -> None:
    webview.on_program_window = loads_and_closes
    shown: list[str] = []

    def start(splash: Splash) -> int:
        splash.status("data")
        splash.show(ADDRESS, tmp_path / "window")
        shown.append("closed")
        return 5

    assert window.run_with_splash(start, tmp_path / "window", "0.7.3") == 5
    assert shown == ["closed"]
    [(card_args, card), (program_args, program)] = webview.created
    assert card_args == ("Rhinvoice",)
    assert "Version 0.7.3 · Beta" in str(card["html"])
    assert card["frameless"] is True
    assert card["resizable"] is False
    # Both windows open in the middle of the main screen (Windows puts them top left).
    assert card["screen"] is MAIN
    steps = card["js_api"]
    assert isinstance(steps, StartSteps)
    assert steps.current() == "data"
    assert program_args == ("Rhinvoice", ADDRESS)
    assert program == {
        "width": 1280,
        "height": 860,
        "x": None,
        "y": None,
        "screen": MAIN,
        "maximized": False,
        "min_size": (960, 640),
        "zoomable": True,
    }
    # The login survives a restart; files are saved, other sites open in the browser.
    assert webview.started == [{"private_mode": False, "storage_path": str(tmp_path / "window")}]
    assert webview.settings == {"ALLOW_DOWNLOADS": True, "OPEN_EXTERNAL_LINKS_IN_BROWSER": True}
    assert webview.windows == []


def test_a_start_that_fails_closes_the_card(tmp_path: Path, webview: FakeWebview) -> None:
    assert window.run_with_splash(lambda _splash: 1, tmp_path / "window", "0.7.3") == 1
    assert webview.windows == []


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_start_that_breaks_ends_with_an_error(tmp_path: Path, webview: FakeWebview) -> None:
    def broken(_splash: Splash) -> int:
        raise RuntimeError

    assert window.run_with_splash(broken, tmp_path / "window", "0.7.3") == window.FAILED
    assert webview.windows == []


def test_asked_to_end_the_start_leaves_its_window_first(
    tmp_path: Path, webview: FakeWebview
) -> None:
    """Ctrl+C reaches the window loop; the start still stops its server and database."""
    webview.interrupt = True
    left: list[str] = []

    def start(splash: Splash) -> int:
        splash.show(ADDRESS, tmp_path / "window")
        left.append("left")
        return 0

    with pytest.raises(KeyboardInterrupt):
        window.run_with_splash(start, tmp_path / "window", "0.7.3")
    assert left == ["left"]


def test_a_window_loop_that_does_not_start_runs_nothing(
    tmp_path: Path, webview: FakeWebview, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError

    monkeypatch.setattr(webview, "start", broken)
    with pytest.raises(RuntimeError):
        window.run_with_splash(lambda _splash: 0, tmp_path / "window", "0.7.3")


def test_without_a_card_the_start_runs_all_the_same(tmp_path: Path, webview: FakeWebview) -> None:
    webview.without_window = True
    assert window.run_with_splash(lambda _splash: 3, tmp_path / "window", "0.7.3") == 3


def test_on_macos_the_closed_windows_go_before_the_program_waits(
    tmp_path: Path, webview: FakeWebview, cocoa: Cocoa
) -> None:
    """After an update the boot waits for the new version: no window may stay meanwhile."""
    webview.on_program_window = loads_and_closes

    def start(splash: Splash) -> int:
        splash.show(ADDRESS, tmp_path / "window")
        return 75

    assert window.run_with_splash(start, tmp_path / "window", "0.8.1") == 75
    # The run loop turned (it takes the windows off the screen), then the Dock icon went.
    assert cocoa.loop.turns
    assert set(cocoa.loop.turns) == {window.LOOP_SLICE_SECONDS}
    assert cocoa.application.policies == [window.NO_DOCK_ICON]


def test_on_macos_the_run_loop_turns_until_the_start_has_ended(cocoa: Cocoa) -> None:
    """The start closes its windows and stops the database meanwhile."""
    ended = threading.Event()
    cocoa.loop.during = lambda turn: ended.set() if turn == 3 else None
    worker = threading.Thread(target=ended.wait)
    worker.start()
    window.wait_for_start(worker, "Darwin", settle=0)
    assert not worker.is_alive()
    assert len(cocoa.loop.turns) >= 3
    assert cocoa.application.policies == [window.NO_DOCK_ICON]


def test_on_macos_the_run_loop_turns_a_while_after_a_quick_end(cocoa: Cocoa) -> None:
    worker = threading.Thread(target=lambda: None)
    worker.start()
    worker.join()
    began = time.monotonic()
    window.wait_for_start(worker, "Darwin", settle=0.05)
    assert time.monotonic() - began >= 0.05
    assert cocoa.loop.turns


def test_elsewhere_the_program_only_waits_for_the_start() -> None:
    worker = threading.Thread(target=lambda: None)
    worker.start()
    window.wait_for_start(worker, "Windows")  # no pyobjc needed
    assert not worker.is_alive()


def test_only_the_program_closes_the_card() -> None:
    """Quitting while it starts would leave the database running."""
    card = Created(FakeWebview(), {})
    splash = Splash(card, StartSteps())
    card.events.closing += splash.may_close
    card.destroy()  # Cmd+Q
    assert not card.destroyed.is_set()
    splash.close()
    splash.close()  # once only
    assert card.destroyed.is_set()
    Splash(None, StartSteps()).close()  # no card: nothing to close


def test_the_card_asks_for_the_current_step() -> None:
    steps = StartSteps()
    assert steps.current() == "database"
    Splash(None, steps).status("ready")
    assert steps.current() == "ready"


def test_rhinvoice_beta_names_itself_in_its_windows(tmp_path: Path, webview: FakeWebview) -> None:
    """ADR 0030: beside Rhinvoice, its windows must not be mistaken for the released one."""
    webview.on_program_window = loads_and_closes

    def start(splash: Splash) -> int:
        splash.show(ADDRESS, tmp_path / "window")
        return 0

    assert window.run_with_splash(start, tmp_path / "window", "0.9.0", "Rhinvoice Beta") == 0
    [(card_args, card), (program_args, _program)] = webview.created
    assert card_args == ("Rhinvoice Beta",)
    assert '<div class="name">Rhinvoice Beta</div>' in str(card["html"])
    assert "<title>Rhinvoice Beta</title>" in str(card["html"])
    assert program_args == ("Rhinvoice Beta", ADDRESS)


def test_the_card_needs_nothing_from_elsewhere() -> None:
    page = window.splash_html("1<2")
    assert "Version 1&lt;2 · Beta" in page
    assert "Datenbank wird gestartet …" in page
    assert "Webberz" not in page
    assert "http" not in page


def test_the_card_of_rhinvoice_beta_shows_its_icon() -> None:
    assert 'id="s"' in window.splash_html("0.8.3", "Rhinvoice Beta")
    assert 'id="s"' not in window.splash_html("0.8.3")


def test_a_closed_window_ends_the_program_window(tmp_path: Path, webview: FakeWebview) -> None:
    ended = threading.Event()
    ended.set()
    (tmp_path / "window").mkdir()
    (tmp_path / "window" / window.FORWARD_REQUEST).touch()  # left by a start while none ran
    window.show(ADDRESS, tmp_path / "window", ended=ended)
    assert webview.window.events.loaded.added == []
    assert not (tmp_path / "window" / window.FORWARD_REQUEST).exists()


def test_closing_or_quitting_goes_through_a_closed_window(
    tmp_path: Path, webview: FakeWebview
) -> None:
    """Cmd+Q would end the process before the program stops its database."""
    ended = threading.Event()
    ended.set()
    window.show(ADDRESS, tmp_path / "window", ended=ended)
    [may_close] = webview.window.events.closing.added
    assert may_close() is False  # not at once ...
    assert webview.window.destroyed.wait(5)  # ... but the window closes just after
    assert may_close() is True  # that close is let through (Windows asks again)


def test_without_a_window_there_is_nothing_to_show(tmp_path: Path, webview: FakeWebview) -> None:
    webview.without_window = True
    window.show(ADDRESS, tmp_path / "window")
    assert webview.window.events.closing.added == []


def test_a_second_start_brings_the_window_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(window, "FORWARD_POLL_SECONDS", 0.01)
    shown = Created(FakeWebview(), {})
    closed = threading.Event()
    storage = tmp_path / "window"
    watcher = threading.Thread(
        target=window.forward_on_request, args=(shown, storage / window.FORWARD_REQUEST, closed)
    )
    watcher.start()
    time.sleep(0.05)  # a few looks without a request first
    window.ask_to_bring_forward(storage)
    deadline = time.monotonic() + 5
    while not shown.raised and time.monotonic() < deadline:
        time.sleep(0.01)
    closed.set()
    watcher.join()
    assert shown.raised == ["restore", "show", "on_top=True", "on_top=False"]
    assert not (storage / window.FORWARD_REQUEST).exists()


def missing(_name: str) -> None:
    """Find no module."""


def test_windows_are_available_with_pywebview(monkeypatch: pytest.MonkeyPatch) -> None:
    assert window.available()
    monkeypatch.setattr(importlib.util, "find_spec", missing)
    assert not window.available()


def test_closing_destroys_every_window(webview: FakeWebview) -> None:
    first = webview.create_window("Rhinvoice")
    second = webview.create_window("Rhinvoice")
    window.close()
    assert first is not None
    assert second is not None
    assert first.destroyed.is_set()
    assert second.destroyed.is_set()


def test_the_main_screen_is_the_one_at_the_origin() -> None:
    assert window.main_screen([Screen(-1920, 0), MAIN]) is MAIN
    # None: pywebview places the window itself.
    assert window.main_screen([Screen(0, 40)]) is None
    assert window.main_screen([]) is None


def moves_and_closes(where: tuple[int, int, int, int], *events: str) -> Callable[[Created], None]:
    """Move and resize the window, maximize or restore it, then close it."""

    def act(shown: Created) -> None:
        handled(shown)
        shown.geometry = where
        for event in events:
            getattr(shown.events, event).fire()
        shown.destroy()

    return act


def program_place(webview: FakeWebview) -> dict[str, object]:
    """How the last program window was made: its size and place."""
    _args, kwargs = webview.created[-1]
    return {key: kwargs[key] for key in ("width", "height", "x", "y", "screen", "maximized")}


def test_the_window_opens_where_it_was_closed(tmp_path: Path, webview: FakeWebview) -> None:
    storage = tmp_path / "window"
    webview.on_program_window = moves_and_closes((100, 50, 1000, 700))
    window.show(ADDRESS, storage)
    assert json.loads((storage / window.GEOMETRY_FILE).read_text()) == {
        "x": 100,
        "y": 50,
        "width": 1000,
        "height": 700,
        "maximized": False,
    }
    window.show(ADDRESS, storage)
    assert program_place(webview) == {
        "width": 1000,
        "height": 700,
        "x": 100,
        "y": 50,
        "screen": None,
        "maximized": False,
    }


def test_a_maximized_window_opens_maximized_and_restores_to_its_size(
    tmp_path: Path, webview: FakeWebview
) -> None:
    storage = tmp_path / "window"
    webview.on_program_window = moves_and_closes((100, 50, 1000, 700))
    window.show(ADDRESS, storage)
    # Maximized, the window is as large as the screen: the size before is kept.
    webview.on_program_window = moves_and_closes((0, 0, 2560, 1440), "maximized")
    window.show(ADDRESS, storage)
    webview.on_program_window = moves_and_closes((0, 0, 2560, 1440))
    window.show(ADDRESS, storage)
    assert program_place(webview) == {
        "width": 1000,
        "height": 700,
        "x": 100,
        "y": 50,
        "screen": None,
        "maximized": True,
    }
    # Restored and closed: the window's own size again, no longer maximized.
    webview.on_program_window = moves_and_closes((200, 80, 1100, 760), "restored")
    window.show(ADDRESS, storage)
    assert json.loads((storage / window.GEOMETRY_FILE).read_text()) == {
        "x": 200,
        "y": 80,
        "width": 1100,
        "height": 760,
        "maximized": False,
    }


def test_a_maximized_window_without_an_earlier_size_keeps_nothing(
    tmp_path: Path, webview: FakeWebview
) -> None:
    storage = tmp_path / "window"
    webview.on_program_window = moves_and_closes((0, 0, 2560, 1440), "maximized")
    window.show(ADDRESS, storage)
    assert not (storage / window.GEOMETRY_FILE).exists()


def test_a_window_that_cannot_tell_where_it_is_keeps_nothing(
    tmp_path: Path, webview: FakeWebview
) -> None:
    storage = tmp_path / "window"

    def lost(shown: Created) -> None:
        handled(shown)
        shown.geometry = None
        shown.destroy()

    webview.on_program_window = lost
    window.show(ADDRESS, storage)
    assert not (storage / window.GEOMETRY_FILE).exists()


@pytest.mark.parametrize(
    "saved",
    [
        '{"x": 5000, "y": 50, "width": 1000, "height": 700}',  # on a screen unplugged since
        '{"x": -32000, "y": -32000, "width": 1000, "height": 700}',  # minimized on Windows
        '{"x": 100, "y": 50, "width": 400, "height": 700}',  # narrower than the window may be
        '{"x": 100, "y": 50, "width": 1000, "height": 300}',  # lower than it may be
        '{"x": 100, "y": 900, "width": 1000, "height": 700}',  # its middle below the screen
        '{"x": 100, "y": 50, "width": 1000}',
        '{"x": "left", "y": 50, "width": 1000, "height": 700}',
        "[1, 2, 3, 4]",
        "not json",
    ],
)
def test_a_place_that_does_not_show_opens_as_on_the_first_start(tmp_path: Path, saved: str) -> None:
    (tmp_path / window.GEOMETRY_FILE).write_text(saved)
    keeper = window.GeometryKeeper(tmp_path / window.GEOMETRY_FILE)
    assert keeper.place([Screen(0, 0, 1920, 1080)]) == window.Place(
        1280, 860, screen=Screen(0, 0, 1920, 1080)
    )


def test_a_place_on_another_screen_is_kept(tmp_path: Path) -> None:
    saved = {"x": -1800, "y": 100, "width": 1000, "height": 700, "maximized": False}
    (tmp_path / window.GEOMETRY_FILE).write_text(json.dumps(saved))
    keeper = window.GeometryKeeper(tmp_path / window.GEOMETRY_FILE)
    assert keeper.place([MAIN, Screen(-1920, 0)]) == window.Place(1000, 700, -1800, 100)


def test_a_place_that_cannot_be_written_is_let_go(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("")
    keeper = window.GeometryKeeper(tmp_path / "file" / window.GEOMETRY_FILE)
    keeper.save(Created(FakeWebview(), {}))  # the folder is a file: nothing kept or raised
    assert (tmp_path / "file").is_file()


def test_a_close_without_anything_before_it_closes_all_the_same() -> None:
    destroyed = threading.Event()
    may_close = window.close_cleanly(destroyed.set)
    assert may_close() is False
    assert destroyed.wait(5)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_failure_before_the_close_still_closes() -> None:
    destroyed = threading.Event()

    def broken() -> None:
        raise RuntimeError

    may_close = window.close_cleanly(destroyed.set, before=broken)
    assert may_close() is False
    assert destroyed.wait(5)
    # The error leaves the timer's thread only after the close: wait for it here, or it is
    # reported in the next test, where the warning filter above does not apply.
    for thread in threading.enumerate():
        if isinstance(thread, threading.Timer):
            thread.join(5)
