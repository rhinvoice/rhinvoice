from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from rhinvoice.application.identity.handlers import (
    ChangePassword,
    CreateUser,
    IdentityHandlers,
    Login,
    hash_token,
)
from rhinvoice.domain.identity.session import Session
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from rhinvoice.infrastructure.security import Argon2PasswordHasher, PyOtpTotpService
from tests.helpers import raises_exactly

NOW = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
PASSWORD = "correct horse battery"


@pytest.fixture
def handlers(engine: Engine) -> IdentityHandlers:
    return IdentityHandlers(
        uow=lambda: SqlUnitOfWork(engine),
        hasher=Argon2PasswordHasher(),
        totp=PyOtpTotpService(),
        clock=FixedClock(NOW),
    )


def test_user_round_trip(engine: Engine, handlers: IdentityHandlers) -> None:
    user = handlers.create_user(
        CreateUser(email="anna@example.com", display_name="Anna", password=PASSWORD),
    )
    locked = user.register_failed_login(NOW).start_totp_setup("PENDING")
    with SqlUnitOfWork(engine) as uow:
        assert uow.users.count() == 1
        assert uow.users.get(user.id) == user
        assert uow.users.get_by_email(EmailAddress("anna@example.com")) == user
        assert uow.users.get(new_id()) is None
        assert uow.users.get_by_email(EmailAddress("nobody@example.com")) is None
        uow.users.update(locked)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.users.get(user.id) == locked


def test_uncommitted_changes_are_rolled_back(engine: Engine, handlers: IdentityHandlers) -> None:
    user = handlers.create_user(
        CreateUser(email="anna@example.com", display_name="Anna", password=PASSWORD),
    )
    with SqlUnitOfWork(engine) as uow:
        uow.users.update(user.with_password_hash("changed"))
    with SqlUnitOfWork(engine) as uow:
        stored = uow.users.get(user.id)
        assert stored is not None
        assert stored.password_hash == user.password_hash


def test_unit_of_work_requires_with_block(engine: Engine) -> None:
    uow = SqlUnitOfWork(engine)
    with raises_exactly(RuntimeError, "unit of work used outside of a with block"):
        uow.commit()


def test_unit_of_work_can_commit_twice(engine: Engine, handlers: IdentityHandlers) -> None:
    user = handlers.create_user(
        CreateUser(email="anna@example.com", display_name="Anna", password=PASSWORD),
    )
    with SqlUnitOfWork(engine) as uow:
        uow.users.update(user.with_password_hash("first"))
        uow.commit()
        uow.users.update(user.with_password_hash("second"))
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        stored = uow.users.get(user.id)
        assert stored is not None
        assert stored.password_hash == "second"


def test_session_repository(engine: Engine, handlers: IdentityHandlers) -> None:
    user = handlers.create_user(
        CreateUser(email="anna@example.com", display_name="Anna", password=PASSWORD),
    )
    first = Session(token_hash="a" * 64, user_id=user.id, created_at=NOW, last_seen_at=NOW)
    second = Session(token_hash="b" * 64, user_id=user.id, created_at=NOW, last_seen_at=NOW)
    third = Session(token_hash="c" * 64, user_id=user.id, created_at=NOW, last_seen_at=NOW)
    with SqlUnitOfWork(engine) as uow:
        for session in (first, second, third):
            uow.sessions.add(session)
        uow.sessions.update(first.touch(NOW + timedelta(hours=1)))
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.sessions.get(first.token_hash) == first.touch(NOW + timedelta(hours=1))
        assert uow.sessions.get("missing") is None
        uow.sessions.delete(third.token_hash)
        assert uow.sessions.get(third.token_hash) is None
        uow.sessions.delete_for_user(user.id, except_token_hash=first.token_hash)
        assert uow.sessions.get(first.token_hash) is not None
        assert uow.sessions.get(second.token_hash) is None
        uow.sessions.delete_for_user(user.id)
        assert uow.sessions.get(first.token_hash) is None


def test_full_login_flow_with_real_adapters(handlers: IdentityHandlers) -> None:
    handlers.create_user(
        CreateUser(email="anna@example.com", display_name="Anna", password=PASSWORD),
    )
    result = handlers.login(Login(email="anna@example.com", password=PASSWORD))
    assert handlers.authenticate(result.token) == result.user
    handlers.change_password(
        ChangePassword(
            user_id=result.user.id,
            current_password=PASSWORD,
            new_password="a completely new password",
            current_token=result.token,
        ),
    )
    assert handlers.authenticate(result.token) is not None
    assert len(hash_token(result.token)) == 64
    handlers.logout(result.token)
    assert handlers.authenticate(result.token) is None


def test_for_update_locks_the_user_row(engine: Engine, handlers: IdentityHandlers) -> None:
    """A second transaction must wait for the first one (lockout counter is not lost)."""
    user = handlers.create_user(
        CreateUser(email="anna@example.com", display_name="Anna", password=PASSWORD),
    )
    with SqlUnitOfWork(engine) as first:
        assert first.users.get_by_email(user.email, for_update=True) is not None
        with engine.connect() as other:
            other.execute(text("SET lock_timeout = '200ms'"))
            with pytest.raises(OperationalError, match="lock timeout"):
                other.execute(
                    text("SELECT id FROM users WHERE id = :id FOR UPDATE"),
                    {"id": user.id},
                )
        assert first.users.get(user.id, for_update=True) is not None


def test_totp_last_step_is_persisted(engine: Engine, handlers: IdentityHandlers) -> None:
    user = handlers.create_user(
        CreateUser(email="anna@example.com", display_name="Anna", password=PASSWORD),
    )
    with SqlUnitOfWork(engine) as uow:
        uow.users.update(user.with_totp_step(123))
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        stored = uow.users.get(user.id)
        assert stored is not None
        assert stored.totp_last_step == 123
