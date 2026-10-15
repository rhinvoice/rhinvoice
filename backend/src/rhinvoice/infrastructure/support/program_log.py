"""The program's log file and the name of the system, for a problem report."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

TAIL_BYTES = 256 * 1024
"""Read from the end only: the log grows with every start and is never cut."""


class ProgramLogFile:
    def __init__(self, path: Path) -> None:
        self._path = path

    def last_lines(self, count: int) -> str:
        try:
            with self._path.open("rb") as log:
                size = log.seek(0, 2)
                log.seek(max(0, size - TAIL_BYTES))
                tail = log.read()
        except FileNotFoundError:
            return ""
        lines = tail.decode("utf-8", errors="replace").splitlines()
        if size > TAIL_BYTES:
            lines = lines[1:]  # the first one starts in the middle
        return "\n".join(lines[-count:])


def system_name(system: str, release: str, machine: str, mac_version: str) -> str:
    """Name the system as people know it: "Windows 11 (AMD64)", "macOS 15.1 (arm64)".

    The arguments come from the platform module (system, release, machine, mac_ver).
    """
    if system == "Darwin" and mac_version:
        return f"macOS {mac_version} ({machine})"
    return f"{system} {release} ({machine})"
