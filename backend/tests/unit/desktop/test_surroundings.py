"""Data folder, configuration and browser of an installation without Docker."""

import json
import stat
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from rhinvoice.desktop.browser import browser_candidates, find_chromium
from rhinvoice.desktop.config import ConfigError, DesktopConfig, load_or_create, update
from rhinvoice_boot import data_folder
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


def test_the_backup_settings_are_kept(tmp_path: Path) -> None:
    path = tmp_path / "rhinvoice.json"
    values = {
        "database_password": "x",
        "backup_folder": "/Users/anna/Dropbox/Rhinvoice-Backup",
        "backup_key": "K7QM-2XWP",
        "backup_key_confirmed": True,
    }
    path.write_text(json.dumps(values))
    assert load_or_create(path) == DesktopConfig(
        database_password="x",
        backup_folder="/Users/anna/Dropbox/Rhinvoice-Backup",
        backup_key="K7QM-2XWP",
        backup_key_confirmed=True,
    )


@pytest.mark.parametrize(
    ("written", "channel"),
    [(None, "stable"), ("test", "test"), ("stable", "stable"), ("beta", "stable"), (1, "stable")],
)
def test_the_update_channel_is_test_only_when_it_says_so(
    tmp_path: Path, written: object, channel: str
) -> None:
    path = tmp_path / "rhinvoice.json"
    values: dict[str, object] = {"database_password": "x"}
    if written is not None:
        values["update_channel"] = written
    path.write_text(json.dumps(values))
    assert load_or_create(path).update_channel == channel


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("{", "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"),
        ("[]", "not a JSON object"),
        ('{"port": 1}', "'database_password' is missing"),
        ('{"database_password": "x", "port": "8000"}', "'port' is not a number"),
        ('{"database_password": "x", "backup_folder": 1}', "'backup_folder' is not text"),
        (
            '{"database_password": "x", "backup_key_confirmed": "yes"}',
            "'backup_key_confirmed' is not true or false",
        ),
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


def test_changes_from_several_threads_are_all_kept(tmp_path: Path) -> None:
    """The API's threads and the backup job change rhinvoice.json at the same time."""
    path = tmp_path / "data" / "rhinvoice.json"
    load_or_create(path)

    def confirm() -> None:
        update(path, lambda config: replace(config, backup_key_confirmed=True))

    def verify() -> None:
        update(path, lambda config: replace(config, backup_verified_at="2026-03-09T10:00:00+00:00"))

    def move(port: int) -> None:
        update(path, lambda config: replace(config, port=port))

    threads = [threading.Thread(target=confirm), threading.Thread(target=verify)]
    threads += [threading.Thread(target=move, args=(9000 + n,)) for n in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    config = load_or_create(path)
    assert config.backup_key_confirmed
    assert config.backup_verified_at == "2026-03-09T10:00:00+00:00"
    assert 9000 <= config.port < 9020
    # Written whole or not at all: no half-written file, no temporary left behind.
    assert [file.name for file in path.parent.iterdir()] == ["rhinvoice.json"]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
