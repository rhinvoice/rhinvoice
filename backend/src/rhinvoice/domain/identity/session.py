"""Server side login sessions.

Only the SHA-256 hash of the session token is stored, so a leaked database
does not leak usable session cookies.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

IDLE_TIMEOUT = timedelta(days=7)
ABSOLUTE_TIMEOUT = timedelta(days=30)
TOUCH_INTERVAL = timedelta(minutes=1)
"""last_seen_at is written at most once per interval to avoid a write per request."""


@dataclass(frozen=True, slots=True)
class Session:
    token_hash: str
    user_id: UUID
    created_at: datetime
    last_seen_at: datetime

    def is_valid(self, now: datetime) -> bool:
        return now - self.last_seen_at < IDLE_TIMEOUT and now - self.created_at < ABSOLUTE_TIMEOUT

    def needs_touch(self, now: datetime) -> bool:
        return now - self.last_seen_at >= TOUCH_INTERVAL

    def touch(self, now: datetime) -> Session:
        return replace(self, last_seen_at=now)
