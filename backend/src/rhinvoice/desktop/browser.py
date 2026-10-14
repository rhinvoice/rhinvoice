"""The browser that prints the PDFs of an installation without Docker.

The installer may bring its own headless Chromium; otherwise Edge (part of every
Windows 10 and 11) or an installed Chrome prints the pages.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def find_chromium(system: str, environ: Mapping[str, str], install: Path) -> Path | None:
    """Find the first browser that exists: the bundled one, then the system's."""
    candidates = browser_candidates(system, environ, install)
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def browser_candidates(system: str, environ: Mapping[str, str], install: Path) -> list[Path]:
    return [
        install / "chromium" / "chrome-headless-shell.exe",
        install / "chromium" / "chrome-headless-shell",
        *_installed(system, environ),
    ]


def _installed(system: str, environ: Mapping[str, str]) -> list[Path]:
    if system == "Windows":
        folders = [
            environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            environ.get("PROGRAMFILES", r"C:\Program Files"),
            environ.get("LOCALAPPDATA", ""),
        ]
        programs = [
            Path("Microsoft", "Edge", "Application", "msedge.exe"),
            Path("Google", "Chrome", "Application", "chrome.exe"),
        ]
        return [Path(folder) / program for program in programs for folder in folders if folder]
    if system == "Darwin":
        return [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    return [
        Path("/usr/bin/chromium"),
        Path("/usr/bin/chromium-browser"),
        Path("/usr/bin/google-chrome"),
        Path("/usr/bin/microsoft-edge"),
    ]
