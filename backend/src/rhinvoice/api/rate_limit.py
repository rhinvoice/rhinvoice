"""Requests per client in a fixed time window, for the public demo.

A normal installation sits behind its owner's proxy and needs none; a public demo is
open to anyone, and its shared login must not be flooded.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

MAX_CLIENTS = 10_000
"""Above this many tracked clients the expired ones are forgotten."""


class RateLimiter:
    """Allow ``limit`` requests per key within ``window`` seconds."""

    def __init__(
        self, limit: int, window: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = limit
        self._window = window
        self._clock = clock
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[float, int]] = {}

    @property
    def clients(self) -> int:
        """How many clients are being tracked."""
        return len(self._counts)

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            started, count = self._counts.get(key, (now, 0))
            if now - started >= self._window:
                started, count = now, 0
            if count >= self._limit:
                return False
            self._counts[key] = (started, count + 1)
            if len(self._counts) > MAX_CLIENTS:
                self._forget_expired(now)
            return True

    def _forget_expired(self, now: float) -> None:
        self._counts = {
            key: value for key, value in self._counts.items() if now - value[0] < self._window
        }


@dataclass(frozen=True, slots=True)
class DemoLimits:
    """Limits of the public demo, per client address."""

    logins: RateLimiter
    changes: RateLimiter

    @classmethod
    def default(cls) -> DemoLimits:
        return cls(logins=RateLimiter(10, 60), changes=RateLimiter(60, 60))
