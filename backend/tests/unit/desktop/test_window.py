"""The program window, against a stand-in for pywebview."""

import importlib.util
import sys
import threading
import types
from collections.abc import Callable
from pathlib import Path
from typing import Self

import pytest

from rhinvoice.desktop import window


class Shown:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class Handlers:
    """pywebview's event: handlers are added with +=."""

    def __init__(self) -> None:
        self.added: list[Callable[[], bool]] = []

    def __iadd__(self, handler: Callable[[], bool]) -> Self:
        self.added.append(handler)
        return self


class Events:
    def __init__(self) -> None:
        self.closing = Handlers()


class Created:
    def __init__(self) -> None:
        self.events = Events()
        self.destroyed = threading.Event()

    def destroy(self) -> None:
        self.destroyed.set()


class FakeWebview(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("webview")
        self.settings: dict[str, object] = {}
        self.created: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.started: list[dict[str, object]] = []
        self.windows: list[Shown] = []
        self.without_window = False
        """The open windows, as pywebview lists them."""

    def create_window(self, *args: object, **kwargs: object) -> Created | None:
        self.created.append((args, kwargs))
        self.window = Created()
        # pywebview returns None when it could not make a window.
        return None if self.without_window else self.window

    def start(self, **kwargs: object) -> None:
        self.started.append(kwargs)


def test_the_window_shows_the_address_and_keeps_its_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    webview = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", webview)
    window.show("http://127.0.0.1:8000", tmp_path / "window")
    assert webview.created == [
        (
            ("Rhinvoice", "http://127.0.0.1:8000"),
            {"width": 1280, "height": 860, "min_size": (960, 640), "zoomable": True},
        )
    ]
    assert webview.started == [{"private_mode": False, "storage_path": str(tmp_path / "window")}]
    assert webview.settings == {"ALLOW_DOWNLOADS": True, "OPEN_EXTERNAL_LINKS_IN_BROWSER": True}


def missing(_name: str) -> None:
    """Find no module."""


def test_windows_are_available_with_pywebview(monkeypatch: pytest.MonkeyPatch) -> None:
    assert window.available()
    monkeypatch.setattr(importlib.util, "find_spec", missing)
    assert not window.available()


def test_closing_destroys_every_window(monkeypatch: pytest.MonkeyPatch) -> None:
    webview = FakeWebview()
    webview.windows = [Shown(), Shown()]
    monkeypatch.setitem(sys.modules, "webview", webview)
    window.close()
    assert [shown.destroyed for shown in webview.windows] == [True, True]


def test_closing_or_quitting_goes_through_a_closed_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cmd+Q would end the process before the program stops its database."""
    webview = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", webview)
    window.show("http://127.0.0.1:8000", tmp_path / "window")
    [may_close] = webview.window.events.closing.added
    assert may_close() is False  # not at once ...
    assert webview.window.destroyed.wait(5)  # ... but the window closes just after
    assert may_close() is True  # that close is let through (Windows asks again)


def test_without_a_window_there_is_nothing_to_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    webview = FakeWebview()
    webview.without_window = True
    monkeypatch.setitem(sys.modules, "webview", webview)
    window.show("http://127.0.0.1:8000", tmp_path / "window")
    assert webview.window.events.closing.added == []
