"""Where the requests of the Idempotency-Keys are remembered (ADR 0041)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from rhinvoice.domain.idempotency.request import StoredRequest


class IdempotencyRepository(Protocol):
    def forget_before(self, at: datetime) -> None:
        """Forget the keys stored before ``at``."""
        ...

    def claim(self, user_id: UUID, key: UUID, request: str, at: datetime) -> StoredRequest | None:
        """Store the key as running, unless it is known: then return what is stored."""
        ...

    def complete(self, user_id: UUID, key: UUID, status_code: int, body: bytes | None) -> None: ...

    def release(self, user_id: UUID, key: UUID) -> None:
        """Forget the key: its request failed and may run again."""
        ...
