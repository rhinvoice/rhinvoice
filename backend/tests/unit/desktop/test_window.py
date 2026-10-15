"""The program window and the start card, against a stand-in for pywebview."""

import importlib.util
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


class Created:
    """A window as pywebview makes it: closing may be refused, closed is told."""

    def __init__(self, webview: "FakeWebview", kwargs: dict[str, object]) -> None:
        self.webview = webview
        self.kwargs = kwargs
        self.events = Events()
        self.destroyed = threading.Event()
        self.raised: list[str] = []
        self._on_top = False

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


MAIN = Screen(0, 0)


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
        "min_size": (960, 640),
        "zoomable": True,
        "screen": MAIN,
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


def test_the_card_needs_nothing_from_elsewhere() -> None:
    page = window.splash_html("1<2")
    assert "Version 1&lt;2 · Beta" in page
    assert "Datenbank wird gestartet …" in page
    assert "by Webberz" in page
    assert "http" not in page


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
