"""Where the program keeps its log, for a problem report."""

from __future__ import annotations

from typing import Protocol


class ProgramLog(Protocol):
    def last_lines(self, count: int) -> str:
        """Return up to ``count`` lines from the end of the log; empty when there is none."""
        ...
