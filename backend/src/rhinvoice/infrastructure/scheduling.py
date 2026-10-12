"""A job that runs now and then in the background of the web server."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class PeriodicJob:
    """Run ``job`` after ``first_delay`` seconds, then every ``interval`` seconds.

    A failing run is logged and the next one tries again: the job must be safe
    to repeat (recurring invoices claim each period once in the database).
    """

    def __init__(
        self, job: Callable[[], object], *, interval: float, first_delay: float, name: str
    ) -> None:
        self._job = job
        self._interval = interval
        self._first_delay = first_delay
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 30) -> None:
        """Ask the job to stop and wait for a run in progress to end."""
        self._stopping.set()
        if self._thread.is_alive():
            self._thread.join(timeout)

    def run_once(self) -> None:
        try:
            self._job()
        except Exception:
            logger.exception("%s failed; trying again later", self._thread.name)

    def _loop(self) -> None:
        delay = self._first_delay
        while not self._stopping.wait(delay):
            self.run_once()
            delay = self._interval
