"""The program window, against a stand-in for pywebview."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

from rhinvoice.desktop import window


class Shown:
    def __init__(self) -> None:
        self.destroyed = False

    def destroy(self) -> None:
        self.destroyed = True


class FakeWebview(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("webview")
        self.settings: dict[str, object] = {}
        self.created: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.started: list[dict[str, object]] = []
        self.windows: list[Shown] = []
        """The open windows, as pywebview lists them."""

    def create_window(self, *args: object, **kwargs: object) -> None:
        self.created.append((args, kwargs))

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
            {"width": 1280, "height": 860, "min_size": (960, 640)},
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
