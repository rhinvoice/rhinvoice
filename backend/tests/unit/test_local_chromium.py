"""The local Chromium, against a stand-in that speaks the DevTools protocol (fake_chromium.py)."""

import io
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pypdf import PdfReader

from rhinvoice.api.container import pdf_renderer
from rhinvoice.api.settings import Settings
from rhinvoice.application.errors import UnavailableError
from rhinvoice.infrastructure.rendering.chromium import PRINT_OPTIONS, LocalChromiumPrinter
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer
from rhinvoice.infrastructure.rendering.pdf import ChromiumPdfRenderer, GotenbergPrinter
from tests.helpers import raises_exactly

FAKE = Path(__file__).parent.parent / "fake_chromium.py"
PAGE = "<!doctype html><title>Rechnung</title><p>Grüezi</p>"
FAILED = "the PDF service (local Chromium) failed"


@pytest.fixture(scope="module")
def binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Make an executable that starts the stand-in like a browser.

    Once: macOS checks every new program on its first start (~2 s).
    """
    script = tmp_path_factory.mktemp("browser") / "chromium"
    script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    script.chmod(0o755)
    return script


@pytest.fixture(autouse=True)
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "commands.jsonl"
    monkeypatch.setenv("FAKE_CHROMIUM_LOG", str(path))
    monkeypatch.setenv("FAKE_CHROMIUM", "print")
    return path


@pytest.fixture
def chromium(binary: Path) -> Iterator[LocalChromiumPrinter]:
    browser = LocalChromiumPrinter(binary, start_timeout=10, timeout=2)
    yield browser
    browser.close()


def entries(log: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def methods(log: Path) -> list[object]:
    return [entry["method"] for entry in entries(log) if "params" in entry]


def starts(log: Path) -> int:
    return sum("arguments" in entry for entry in entries(log))


def test_a_page_is_printed_with_the_options_of_gotenberg(
    chromium: LocalChromiumPrinter, log: Path
) -> None:
    content = chromium.print_pdf(PAGE)
    assert len(PdfReader(io.BytesIO(content)).pages) == 1
    assert methods(log) == [
        "Target.createTarget",
        "Target.attachToTarget",
        "Page.enable",
        "Page.navigate",
        "Runtime.evaluate",
        "Page.printToPDF",
        "Target.closeTarget",
    ]
    [arguments] = [entry["arguments"] for entry in entries(log) if "arguments" in entry]
    assert isinstance(arguments, list)
    assert "--headless" in arguments
    assert "--remote-debugging-port=0" in arguments
    [printed] = [e for e in entries(log) if e.get("method") == "Page.printToPDF" and "params" in e]
    assert printed["params"] == PRINT_OPTIONS
    assert printed["sessionId"] == "tab-session"
    # The page reaches the browser unchanged, as a file in its own profile folder.
    [navigation] = [e for e in entries(log) if "page" in e]
    assert navigation["page"] == PAGE


def test_the_browser_keeps_running_between_pages(chromium: LocalChromiumPrinter, log: Path) -> None:
    chromium.print_pdf(PAGE)
    chromium.print_pdf(PAGE)
    assert starts(log) == 1
    chromium.close()
    chromium.print_pdf(PAGE)
    assert starts(log) == 2


@pytest.mark.parametrize(
    "mode",
    [
        "error",
        "hangup",
        "stall",
        "load-error",
        "garbage",
        "not-object",
        "no-target",
        "no-data",
        "not-base64",
        "early-load",
    ],
)
def test_failures_are_reported_and_the_browser_is_started_anew(
    chromium: LocalChromiumPrinter, log: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("FAKE_CHROMIUM", mode)
    with raises_exactly(UnavailableError, FAILED):
        chromium.print_pdf(PAGE)
    monkeypatch.setenv("FAKE_CHROMIUM", "print")
    assert chromium.print_pdf(PAGE).startswith(b"%PDF-")
    assert starts(log) == 2


def test_only_pdfs_are_returned(
    chromium: LocalChromiumPrinter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_CHROMIUM", "not-pdf")
    with raises_exactly(UnavailableError, "the PDF service (local Chromium) did not return a PDF"):
        chromium.print_pdf(PAGE)


def test_a_missing_browser_is_reported(tmp_path: Path) -> None:
    missing = tmp_path / "no-chromium"
    with raises_exactly(
        UnavailableError, f"the PDF service (local Chromium) cannot be started: {missing}"
    ):
        LocalChromiumPrinter(missing).print_pdf(PAGE)


@pytest.mark.parametrize(("mode", "reason"), [("exit", "exit code 1"), ("silent", "no answer")])
def test_a_browser_that_does_not_start_is_reported(
    binary: Path,
    log: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    reason: str,
) -> None:
    monkeypatch.setenv("FAKE_CHROMIUM", mode)
    # A browser that exits is noticed at once: plenty of time for a slow machine to see that.
    chromium = LocalChromiumPrinter(binary, start_timeout=1 if mode == "silent" else 10)
    message = f"the PDF service (local Chromium) did not start: {binary} ({reason})"
    with raises_exactly(UnavailableError, message):
        chromium.print_pdf(PAGE)
    assert log.exists() == (mode == "silent")


def test_a_browser_that_ignores_the_request_to_end_is_killed(
    binary: Path, log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_CHROMIUM", "stubborn")
    chromium = LocalChromiumPrinter(binary, stop_timeout=0.5)
    chromium.print_pdf(PAGE)
    chromium.close()
    chromium.print_pdf(PAGE)
    chromium.close()
    assert starts(log) == 2


def test_the_settings_choose_the_printer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RHINVOICE_GOTENBERG_URL", "RHINVOICE_CHROMIUM_PATH"):
        monkeypatch.delenv(name, raising=False)
    html = JinjaDocumentRenderer()
    assert pdf_renderer(Settings(), html) is None
    chromium = pdf_renderer(Settings(chromium_path=tmp_path / "chrome"), html)
    assert isinstance(chromium, ChromiumPdfRenderer)
    assert isinstance(chromium.printer, LocalChromiumPrinter)
    # The Docker setup keeps Gotenberg, also when a browser is configured as well.
    both = Settings(gotenberg_url="http://gotenberg:3000", chromium_path=tmp_path / "chrome")
    gotenberg = pdf_renderer(both, html)
    assert isinstance(gotenberg, ChromiumPdfRenderer)
    assert isinstance(gotenberg.printer, GotenbergPrinter)
