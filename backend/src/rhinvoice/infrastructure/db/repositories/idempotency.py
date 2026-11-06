"""The requests of the Idempotency-Keys (ADR 0041)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, delete, literal_column, update
from sqlalchemy.dialects.postgresql import insert

from rhinvoice.domain.idempotency.request import KeyState, StoredRequest
from rhinvoice.infrastructure.db.tables import idempotency_keys

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy import Connection


class SqlIdempotencyRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def forget_before(self, at: datetime) -> None:
        self._connection.execute(delete(idempotency_keys).where(idempotency_keys.c.started_at < at))

    def claim(self, user_id: UUID, key: UUID, request: str, at: datetime) -> StoredRequest | None:
        # One statement, so that no other request can come in between: it inserts the key, or
        # (the update changes nothing) locks and returns the row stored already. "xmax = 0"
        # tells PostgreSQL's freshly inserted row from an existing one.
        statement = insert(idempotency_keys).values(
            user_id=user_id,
            key=key,
            fingerprint=request,
            state=KeyState.RUNNING.value,
            started_at=at,
        )
        row = (
            self._connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["user_id", "key"],
                    set_={"user_id": statement.excluded.user_id},
                ).returning(
                    *idempotency_keys.c,
                    literal_column("xmax = 0", Boolean).label("inserted"),
                )
            )
            .mappings()
            .one()
        )
        if row["inserted"]:
            return None
        return StoredRequest(
            fingerprint=row["fingerprint"],
            state=KeyState(row["state"]),
            started_at=row["started_at"],
            status_code=row["status_code"],
            body=row["body"],
        )

    def complete(self, user_id: UUID, key: UUID, status_code: int, body: bytes | None) -> None:
        self._connection.execute(
            update(idempotency_keys)
            .where(idempotency_keys.c.user_id == user_id, idempotency_keys.c.key == key)
            .values(state=KeyState.DONE.value, status_code=status_code, body=body)
        )

    def release(self, user_id: UUID, key: UUID) -> None:
        self._connection.execute(
            delete(idempotency_keys).where(
                idempotency_keys.c.user_id == user_id, idempotency_keys.c.key == key
            )
        )
