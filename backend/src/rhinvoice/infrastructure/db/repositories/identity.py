from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, insert, select, text, update

from rhinvoice.domain.identity.session import Session
from rhinvoice.domain.identity.user import User
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.infrastructure.db.tables import sessions, users

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import Connection, RowMapping, Select


def _user_from_row(row: RowMapping) -> User:
    return User(
        id=row["id"],
        email=EmailAddress(row["email"]),
        display_name=row["display_name"],
        password_hash=row["password_hash"],
        created_at=row["created_at"],
        totp_secret=row["totp_secret"],
        totp_pending_secret=row["totp_pending_secret"],
        failed_logins=row["failed_logins"],
        locked_until=row["locked_until"],
        totp_last_step=row["totp_last_step"],
    )


def _user_values(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email.value,
        "display_name": user.display_name,
        "password_hash": user.password_hash,
        "created_at": user.created_at,
        "totp_secret": user.totp_secret,
        "totp_pending_secret": user.totp_pending_secret,
        "failed_logins": user.failed_logins,
        "locked_until": user.locked_until,
        "totp_last_step": user.totp_last_step,
    }


class SqlUserRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        return self._one(select(users).where(users.c.id == user_id), for_update=for_update)

    def get_by_email(self, email: EmailAddress, *, for_update: bool = False) -> User | None:
        return self._one(select(users).where(users.c.email == email.value), for_update=for_update)

    def _one(self, statement: Select[Any], *, for_update: bool) -> User | None:
        if for_update:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().first()
        return None if row is None else _user_from_row(row)

    def add(self, user: User) -> None:
        self._connection.execute(insert(users).values(_user_values(user)))

    def update(self, user: User) -> None:
        self._connection.execute(
            update(users).where(users.c.id == user.id).values(_user_values(user)),
        )

    def count(self) -> int:
        return self._connection.execute(select(func.count()).select_from(users)).scalar_one()

    def lock(self) -> None:
        self._connection.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))


def _session_from_row(row: RowMapping) -> Session:
    return Session(
        token_hash=row["token_hash"],
        user_id=row["user_id"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
    )


class SqlSessionRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, token_hash: str) -> Session | None:
        row = (
            self._connection.execute(select(sessions).where(sessions.c.token_hash == token_hash))
            .mappings()
            .first()
        )
        return None if row is None else _session_from_row(row)

    def add(self, session: Session) -> None:
        self._connection.execute(
            insert(sessions).values(
                token_hash=session.token_hash,
                user_id=session.user_id,
                created_at=session.created_at,
                last_seen_at=session.last_seen_at,
            ),
        )

    def update(self, session: Session) -> None:
        self._connection.execute(
            update(sessions)
            .where(sessions.c.token_hash == session.token_hash)
            .values(last_seen_at=session.last_seen_at),
        )

    def delete(self, token_hash: str) -> None:
        self._connection.execute(delete(sessions).where(sessions.c.token_hash == token_hash))

    def delete_for_user(self, user_id: UUID, *, except_token_hash: str | None = None) -> None:
        statement = delete(sessions).where(sessions.c.user_id == user_id)
        if except_token_hash is not None:
            statement = statement.where(sessions.c.token_hash != except_token_hash)
        self._connection.execute(statement)
