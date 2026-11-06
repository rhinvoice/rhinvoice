"""Run a request with an Idempotency-Key once (ADR 0041).

Three steps, each committed on its own: the key is claimed before the request runs, so that a
concurrent repeat finds it; the response is stored after it succeeded, or the key released
after it failed. A request cut off between its work and its answer leaves the key running.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rhinvoice.domain.idempotency.request import (
    KEEP,
    MAX_STORED_BODY,
    StoredRequest,
    Verdict,
    judge,
)

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.application.uow import UnitOfWorkFactory
    from rhinvoice.domain.shared.clock import Clock


@dataclass(frozen=True, slots=True)
class Repeat:
    """A known key: what the request gets instead of running."""

    verdict: Verdict
    stored: StoredRequest


@dataclass(frozen=True, slots=True)
class IdempotencyHandlers:
    uow: UnitOfWorkFactory
    clock: Clock

    def begin(self, user_id: UUID, key: UUID, request: str) -> Repeat | None:
        """Claim ``key`` for ``request``; None when it may run, else what it gets instead."""
        now = self.clock.now()
        # Old keys of all users go in a transaction of their own: two claims never wait for
        # each other over them.
        with self.uow() as uow:
            uow.idempotency.forget_before(now - KEEP)
            uow.commit()
        with self.uow() as uow:
            stored = uow.idempotency.claim(user_id, key, request, now)
            uow.commit()
        return None if stored is None else Repeat(judge(stored, request, now), stored)

    def succeed(self, user_id: UUID, key: UUID, status_code: int, body: bytes | None) -> None:
        """Remember the response of the request; one too large is not kept (``body`` None)."""
        kept = body if body is not None and len(body) <= MAX_STORED_BODY else None
        with self.uow() as uow:
            uow.idempotency.complete(user_id, key, status_code, kept)
            uow.commit()

    def fail(self, user_id: UUID, key: UUID) -> None:
        """Free the key of a failed request: corrected, it may run with the same key."""
        with self.uow() as uow:
            uow.idempotency.release(user_id, key)
            uow.commit()
