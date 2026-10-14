"""Data folder, configuration and browser of an installation without Docker."""

import json
import stat
from pathlib import Path

import pytest

from rhinvoice.desktop.browser import browser_candidates, find_chromium
from rhinvoice.desktop.config import ConfigError, DesktopConfig, load_or_create
from rhinvoice.desktop.folders import data_folder
from tests.helpers import raises_exactly

HOME = Path("/home/anna")


@pytest.mark.parametrize(
    ("system", "environ", "folder"),
    [
        (
            "Windows",
            {"LOCALAPPDATA": r"C:\Users\anna\AppData\Local"},
            Path(r"C:\Users\anna\AppData\Local") / "Rhinvoice",
        ),
        ("Windows", {}, HOME / "AppData" / "Local" / "Rhinvoice"),
        ("Darwin", {}, HOME / "Library" / "Application Support" / "Rhinvoice"),
        ("Linux", {"XDG_DATA_HOME": "/data"}, Path("/data/rhinvoice")),
        ("Linux", {}, HOME / ".local" / "share" / "rhinvoice"),
    ],
)
def test_the_data_folder_follows_the_system(
    system: str, environ: dict[str, str], folder: Path
) -> None:
    assert data_folder(system, environ, HOME) == folder


def test_the_first_start_writes_a_private_configuration(tmp_path: Path) -> None:
    path = tmp_path / "data" / "rhinvoice.json"
    config = load_or_create(path)
    assert len(config.database_password) == 48
    assert config.port == 8000
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_or_create(path) == config
    assert load_or_create(tmp_path / "other.json") != config


def test_a_configured_port_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "rhinvoice.json"
    path.write_text(json.dumps({"database_password": "x", "port": 8123}))
    assert load_or_create(path) == DesktopConfig(database_password="x", port=8123)


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("{", "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"),
        ("[]", "not a JSON object"),
        ('{"port": 1}', "'database_password' is missing"),
        ('{"database_password": "x", "port": "8000"}', "'port' is not a number"),
    ],
)
def test_a_damaged_configuration_is_reported(tmp_path: Path, content: str, reason: str) -> None:
    path = tmp_path / "rhinvoice.json"
    path.write_text(content)
    with raises_exactly(ConfigError, f"{path} is damaged: {reason}"):
        load_or_create(path)


def test_the_bundled_browser_comes_first(tmp_path: Path) -> None:
    bundled = tmp_path / "chromium" / "chrome-headless-shell"
    bundled.parent.mkdir()
    assert find_chromium("Linux", {}, tmp_path) in {
        None,
        *browser_candidates("Linux", {}, tmp_path)[2:],
    }
    bundled.write_text("")
    assert find_chromium("Linux", {}, tmp_path) == bundled


def test_on_windows_edge_is_found(tmp_path: Path) -> None:
    edge = tmp_path / "x86" / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_text("")
    environ = {"PROGRAMFILES(X86)": str(tmp_path / "x86"), "PROGRAMFILES": str(tmp_path / "x64")}
    assert find_chromium("Windows", environ, tmp_path / "install") == edge
    assert find_chromium("Windows", {}, tmp_path / "install") is None


def test_browsers_of_each_system() -> None:
    install = Path("/opt/rhinvoice")
    windows = browser_candidates("Windows", {"LOCALAPPDATA": "/users/anna"}, install)
    assert windows[:2] == [
        install / "chromium" / "chrome-headless-shell.exe",
        install / "chromium" / "chrome-headless-shell",
    ]
    assert (
        Path(r"C:\Program Files (x86)") / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        in windows
    )
    assert Path("/users/anna/Google/Chrome/Application/chrome.exe") in windows
    mac = browser_candidates("Darwin", {}, install)
    assert Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") in mac
    linux = browser_candidates("Linux", {}, install)
    assert Path("/usr/bin/chromium") in linux
