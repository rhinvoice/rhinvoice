"""The requests of the Idempotency-Keys in PostgreSQL (ADR 0041)."""

import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError

from rhinvoice.application.idempotency.handlers import IdempotencyHandlers
from rhinvoice.application.identity.handlers import CreateUser, IdentityHandlers
from rhinvoice.domain.idempotency.request import KEEP, KeyState, Verdict, fingerprint
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.infrastructure.db.tables import idempotency_keys
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork
from rhinvoice.infrastructure.security import Argon2PasswordHasher, PyOtpTotpService

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
KEY = UUID("3f2c8a2e-6c1b-4f3e-9a52-0d6b8f1e2a77")
CREATE = fingerprint("POST", "/api/documents", "", b'{"type":"invoice"}')


def user(engine: Engine, email: str = "anna@example.com") -> UUID:
    identity = IdentityHandlers(
        uow=lambda: SqlUnitOfWork(engine),
        hasher=Argon2PasswordHasher(),
        totp=PyOtpTotpService(),
        clock=FixedClock(NOW),
    )
    created = identity.create_user(
        CreateUser(email=email, display_name="Anna", password="correct horse battery")
    )
    return created.id


def handlers(engine: Engine, now: datetime = NOW) -> IdempotencyHandlers:
    return IdempotencyHandlers(uow=lambda: SqlUnitOfWork(engine), clock=FixedClock(now))


def test_a_request_is_claimed_answered_and_replayed(engine: Engine) -> None:
    anna = user(engine)
    assert handlers(engine).begin(anna, KEY, CREATE) is None
    repeat = handlers(engine).begin(anna, KEY, CREATE)
    assert repeat is not None
    assert repeat.verdict is Verdict.IN_PROGRESS
    assert repeat.stored.started_at == NOW
    handlers(engine).succeed(anna, KEY, 201, b'{"id":"1"}')
    repeat = handlers(engine).begin(anna, KEY, CREATE)
    assert repeat is not None
    assert repeat.verdict is Verdict.REPLAY
    assert repeat.stored.state is KeyState.DONE
    assert repeat.stored.status_code == 201
    assert repeat.stored.body == b'{"id":"1"}'


def test_a_failed_request_leaves_nothing(engine: Engine) -> None:
    anna = user(engine)
    assert handlers(engine).begin(anna, KEY, CREATE) is None
    handlers(engine).fail(anna, KEY)
    with engine.connect() as connection:
        count = select(func.count()).select_from(idempotency_keys)
        assert connection.execute(count).scalar_one() == 0


def test_old_keys_are_forgotten_and_a_user_takes_theirs_along(engine: Engine) -> None:
    anna = user(engine)
    ben = user(engine, "ben@example.com")
    assert handlers(engine).begin(anna, KEY, CREATE) is None
    handlers(engine).succeed(anna, KEY, 201, None)
    assert handlers(engine).begin(ben, KEY, CREATE) is None
    later = handlers(engine, NOW + KEEP + timedelta(microseconds=1))
    assert later.begin(anna, UUID(int=1), CREATE) is None
    with engine.connect() as connection:
        keys = connection.execute(select(idempotency_keys.c.key)).scalars().all()
    assert sorted(keys) == [UUID(int=1)]
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": anna})
        count = select(func.count()).select_from(idempotency_keys)
        assert connection.execute(count).scalar_one() == 0


def test_of_two_concurrent_requests_with_one_key_only_one_runs(engine: Engine) -> None:
    anna = user(engine)
    results: list[object] = []
    start = threading.Barrier(2)

    def claim() -> None:
        start.wait()
        results.append(handlers(engine).begin(anna, KEY, CREATE))

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(None) == 1


def test_a_done_key_needs_its_status(engine: Engine) -> None:
    anna = user(engine)
    with (
        pytest.raises(IntegrityError, match="ck_idempotency_keys_done_status"),
        engine.begin() as connection,
    ):
        connection.execute(
            idempotency_keys.insert().values(
                user_id=anna,
                key=KEY,
                fingerprint=CREATE,
                state="done",
                started_at=NOW,
            )
        )
