"""A request repeated with the same Idempotency-Key runs once (ADR 0041).

The key belongs to one intent of a user, e.g. an opened form. The first request with it runs;
a repeat, such as a retry after its response was lost, gets the stored response instead of a
second run. Only successful requests are kept, for as long as a page holding the key may
still be open.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

KEEP = timedelta(days=7)
"""How long a key is remembered: a laptop closed over a weekend with the page still open."""
UNFINISHED_AFTER = timedelta(minutes=10)
"""A request still running after this long was cut off between its work and its answer."""
MAX_STORED_BODY = 1024 * 1024
"""Larger responses (an export, a PDF) are not kept; a repeat is refused instead."""


class KeyState(StrEnum):
    RUNNING = "running"
    DONE = "done"


class Verdict(StrEnum):
    """What a repeated request with a known key gets."""

    REPLAY = "replay"
    """The stored response: the request was done before."""
    DONE = "done"
    """Done before, but its response was too large to keep."""
    IN_PROGRESS = "in_progress"
    """The first request with the key still runs."""
    UNFINISHED = "unfinished"
    """The first request was cut off: whether it did its work is unknown."""
    REUSED = "reused"
    """The key came with another request: a client error, never a repeat."""


@dataclass(frozen=True, slots=True)
class StoredRequest:
    fingerprint: str
    state: KeyState
    started_at: datetime
    status_code: int | None = None
    body: bytes | None = None
    """The response of a done request; None when it was too large to keep."""


class Fingerprint:
    """Identify a request by what it asks for: method, address and body (SHA-256).

    The body is added as it arrives, so that it need not be held in memory.
    """

    def __init__(self, method: str, path: str, query: str) -> None:
        self._digest = hashlib.sha256()
        for part in (method.upper().encode(), path.encode(), query.encode()):
            # Each part with its length: "/a" + "b" is not "/ab" + "".
            self._digest.update(len(part).to_bytes(8))
            self._digest.update(part)

    def update(self, body: bytes) -> None:
        self._digest.update(body)

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def fingerprint(method: str, path: str, query: str, body: bytes) -> str:
    """Identify a request whose body is at hand."""
    whole = Fingerprint(method, path, query)
    whole.update(body)
    return whole.hexdigest()


def judge(stored: StoredRequest, request: str, now: datetime) -> Verdict:
    """Decide what the repeat ``request`` (its fingerprint) of a known key gets."""
    if stored.fingerprint != request:
        return Verdict.REUSED
    if stored.state is KeyState.RUNNING:
        cut_off = now - stored.started_at >= UNFINISHED_AFTER
        return Verdict.UNFINISHED if cut_off else Verdict.IN_PROGRESS
    return Verdict.DONE if stored.body is None else Verdict.REPLAY
