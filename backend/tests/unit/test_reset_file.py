"""The code of a forgotten password as a file only this computer's user reads (ADR 0024)."""

import os
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rhinvoice.infrastructure.identity.reset_file import (
    FILE_NAME,
    OPEN_SECONDS,
    FileResetDelivery,
    open_with_system,
)

UNTIL = datetime(2026, 1, 15, 9, 15, tzinfo=UTC)


def test_the_code_and_the_accounts_are_written_and_shown(tmp_path: Path) -> None:
    opened: list[Path] = []
    delivery = FileResetDelivery(tmp_path, opened.append)
    delivery.deliver("K7QM2-XWP9D", ["anna@example.com", "zora@example.com"], UNTIL)
    path = tmp_path / FILE_NAME
    assert delivery.path == path
    assert opened == [path]
    text = path.read_text(encoding="utf-8")
    until = UNTIL.astimezone().strftime("%H:%M")
    assert "Code: K7QM2-XWP9D\n" in text
    assert f"Gültig bis {until} Uhr, nur einmal." in text
    assert f"Valid until {until}, once." in text
    assert "\n  anna@example.com\n  zora@example.com\n" in text
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    delivery.remove()
    assert not path.exists()
    delivery.remove()  # gone already: nothing to do


def test_a_new_code_replaces_the_file_without_an_opener(tmp_path: Path) -> None:
    delivery = FileResetDelivery(tmp_path)
    delivery.deliver("AAAAA-AAAAA", ["anna@example.com"], UNTIL)
    delivery.deliver("BBBBB-BBBBB", ["anna@example.com"], UNTIL)
    text = (tmp_path / FILE_NAME).read_text(encoding="utf-8")
    assert "AAAAA" not in text
    assert "BBBBB-BBBBB" in text


@pytest.mark.parametrize(
    ("platform", "command"), [("darwin", "/usr/bin/open"), ("linux", "xdg-open")]
)
def test_the_file_opens_with_the_system(
    monkeypatch: pytest.MonkeyPatch, platform: str, command: str
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(sys, "platform", platform)

    def run(args: list[str], **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", run)
    open_with_system(Path("/data/code.txt"))
    assert calls == [([command, "/data/code.txt"], {"check": False, "timeout": OPEN_SECONDS})]


def test_on_windows_the_file_opens_with_its_program(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[Path] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", started.append, raising=False)
    open_with_system(Path("C:/data/code.txt"))
    assert started == [Path("C:/data/code.txt")]


@pytest.mark.parametrize("error", [OSError("no program"), subprocess.TimeoutExpired("open", 10)])
def test_without_a_program_to_open_it_the_file_still_lies_there(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", fail)
    open_with_system(Path("/data/code.txt"))
    assert OPEN_SECONDS == 10
