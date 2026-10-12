from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from rhinvoice.application.errors import (
    AccountLockedError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    TotpRequiredError,
)
from rhinvoice.application.identity.handlers import (
    ChangePassword,
    CreateUser,
    DisableTotp,
    IdentityHandlers,
    Login,
    hash_token,
)
from rhinvoice.domain.identity.session import IDLE_TIMEOUT
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from tests.helpers import raises_exactly
from tests.unit.application.fakes import (
    NEXT_TOTP_CODE,
    TOTP_STEP,
    VALID_TOTP_CODE,
    FakePasswordHasher,
    FakeTotpService,
    InMemoryUnitOfWork,
    Store,
)

PASSWORD = "correct horse battery"
NOW = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def hasher() -> FakePasswordHasher:
    return FakePasswordHasher()


@pytest.fixture
def handlers(store: Store, clock: FixedClock, hasher: FakePasswordHasher) -> IdentityHandlers:
    return IdentityHandlers(
        uow=lambda: InMemoryUnitOfWork(store),
        hasher=hasher,
        totp=FakeTotpService(),
        clock=clock,
    )


def create(handlers: IdentityHandlers, email: str = "anna@example.com") -> None:
    handlers.create_user(CreateUser(email=email, display_name="Anna", password=PASSWORD))


def test_hash_token_is_sha256_hex() -> None:
    assert hash_token("abc") == ("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


def test_create_user(handlers: IdentityHandlers, store: Store) -> None:
    assert not handlers.has_users()
    user = handlers.create_user(
        CreateUser(email=" Anna@Example.com ", display_name="Anna", password=PASSWORD),
    )
    assert handlers.has_users()
    assert store.users == {user.id: user}
    assert str(user.email) == "anna@example.com"
    assert isinstance(user.id, UUID)
    assert user.password_hash == f"hashed:{PASSWORD}"
    assert user.created_at == NOW


def test_create_first_user_only_once(handlers: IdentityHandlers, store: Store) -> None:
    command = CreateUser(email="anna@example.com", display_name="Anna", password=PASSWORD)
    first = handlers.create_first_user(command)
    assert store.users == {first.id: first}
    with raises_exactly(ConflictError, "setup has already been completed"):
        handlers.create_first_user(
            CreateUser(email="ben@example.com", display_name="Ben", password=PASSWORD),
        )


def test_create_user_rejects_duplicates_and_weak_passwords(handlers: IdentityHandlers) -> None:
    create(handlers)
    with raises_exactly(ConflictError, "a user with e-mail anna@example.com already exists"):
        create(handlers, "ANNA@example.com")
    with pytest.raises(ValidationError):
        handlers.create_user(CreateUser(email="b@example.com", display_name="B", password="short"))


def test_login_creates_session(handlers: IdentityHandlers, store: Store) -> None:
    create(handlers)
    result = handlers.login(Login(email="ANNA@example.com", password=PASSWORD))
    assert len(result.token) == 64  # 48 random bytes, base64url encoded
    session = store.sessions[hash_token(result.token)]
    assert session.user_id == result.user.id
    assert session.created_at == NOW
    assert session.last_seen_at == NOW
    assert handlers.authenticate(result.token) == result.user


def test_login_tokens_are_unique(handlers: IdentityHandlers) -> None:
    create(handlers)
    first = handlers.login(Login(email="anna@example.com", password=PASSWORD))
    second = handlers.login(Login(email="anna@example.com", password=PASSWORD))
    assert first.token != second.token


def test_login_unknown_user_hashes_to_equalize_timing(
    handlers: IdentityHandlers,
    hasher: FakePasswordHasher,
) -> None:
    """The submitted password is hashed so the response time matches a known user."""
    with raises_exactly(AuthenticationError, "e-mail or password is incorrect") as error:
        handlers.login(Login(email="nobody@example.com", password=PASSWORD))
    assert error.value.code == "authentication_failed"
    assert hasher.hashed == [PASSWORD]


def test_login_with_malformed_email_is_a_failed_login(
    handlers: IdentityHandlers,
    hasher: FakePasswordHasher,
) -> None:
    with raises_exactly(AuthenticationError, "e-mail or password is incorrect"):
        handlers.login(Login(email="not an email", password=PASSWORD))
    assert hasher.hashed == [PASSWORD]


def test_wrong_password_counts_and_locks(handlers: IdentityHandlers, store: Store) -> None:
    create(handlers)
    for _ in range(5):
        with raises_exactly(AuthenticationError, "e-mail or password is incorrect"):
            handlers.login(Login(email="anna@example.com", password="wrong password"))
    with raises_exactly(AccountLockedError, "too many failed attempts, try again later"):
        handlers.login(Login(email="anna@example.com", password=PASSWORD))
    user = next(iter(store.users.values()))
    assert user.locked_until == NOW + timedelta(minutes=15)


def test_a_public_demo_never_locks_its_shared_login(
    store: Store, clock: FixedClock, hasher: FakePasswordHasher
) -> None:
    handlers = IdentityHandlers(
        uow=lambda: InMemoryUnitOfWork(store),
        hasher=hasher,
        totp=FakeTotpService(),
        clock=clock,
        lockout=False,
    )
    create(handlers)
    for _ in range(10):
        with raises_exactly(AuthenticationError, "e-mail or password is incorrect"):
            handlers.login(Login(email="anna@example.com", password="wrong password"))
    assert next(iter(store.users.values())).failed_logins == 0
    handlers.login(Login(email="anna@example.com", password=PASSWORD))


def test_failed_login_is_persisted(handlers: IdentityHandlers, store: Store) -> None:
    create(handlers)
    with pytest.raises(AuthenticationError):
        handlers.login(Login(email="anna@example.com", password="wrong password"))
    assert next(iter(store.users.values())).failed_logins == 1
    handlers.login(Login(email="anna@example.com", password=PASSWORD))
    assert next(iter(store.users.values())).failed_logins == 0


def test_login_rehashes_outdated_hashes(handlers: IdentityHandlers, store: Store) -> None:
    create(handlers)
    user = next(iter(store.users.values()))
    store.users[user.id] = user.with_password_hash(f"old:{PASSWORD}")
    result = handlers.login(Login(email="anna@example.com", password=PASSWORD))
    assert result.user.password_hash == f"hashed:{PASSWORD}"
    assert store.users[user.id].password_hash == f"hashed:{PASSWORD}"


def test_authenticate_rejects_unknown_and_expired_sessions(
    handlers: IdentityHandlers,
    clock: FixedClock,
    store: Store,
) -> None:
    create(handlers)
    assert handlers.authenticate("unknown") is None
    token = handlers.login(Login(email="anna@example.com", password=PASSWORD)).token
    clock.set(NOW + timedelta(days=1))
    assert handlers.authenticate(token) is not None
    assert store.sessions[hash_token(token)].last_seen_at == NOW + timedelta(days=1)
    clock.set(NOW + timedelta(days=1) + IDLE_TIMEOUT)
    assert handlers.authenticate(token) is None
    assert store.sessions == {}


def test_authenticate_drops_sessions_of_deleted_users(
    handlers: IdentityHandlers,
    store: Store,
) -> None:
    create(handlers)
    token = handlers.login(Login(email="anna@example.com", password=PASSWORD)).token
    store.users.clear()
    assert handlers.authenticate(token) is None
    assert store.sessions == {}


def test_logout(handlers: IdentityHandlers, store: Store) -> None:
    create(handlers)
    token = handlers.login(Login(email="anna@example.com", password=PASSWORD)).token
    handlers.logout(token)
    assert store.sessions == {}
    assert handlers.authenticate(token) is None


def test_get_user(handlers: IdentityHandlers) -> None:
    create(handlers)
    user = handlers.login(Login(email="anna@example.com", password=PASSWORD)).user
    assert handlers.get_user(user.id) == user
    with raises_exactly(NotFoundError, "user not found"):
        handlers.get_user(new_id())


def test_change_password_keeps_only_current_session(
    handlers: IdentityHandlers,
    store: Store,
) -> None:
    create(handlers)
    current = handlers.login(Login(email="anna@example.com", password=PASSWORD))
    other = handlers.login(Login(email="anna@example.com", password=PASSWORD))
    handlers.change_password(
        ChangePassword(
            user_id=current.user.id,
            current_password=PASSWORD,
            new_password="another long password",
            current_token=current.token,
        ),
    )
    assert set(store.sessions) == {hash_token(current.token)}
    assert hash_token(other.token) not in store.sessions
    assert store.users[current.user.id].password_hash == "hashed:another long password"


def test_change_password_requires_current_password(handlers: IdentityHandlers) -> None:
    create(handlers)
    current = handlers.login(Login(email="anna@example.com", password=PASSWORD))
    command = ChangePassword(
        user_id=current.user.id,
        current_password="wrong password",
        new_password="another long password",
        current_token=current.token,
    )
    with raises_exactly(AuthenticationError, "current password is incorrect"):
        handlers.change_password(command)
    with pytest.raises(ValidationError):
        handlers.change_password(
            ChangePassword(
                user_id=current.user.id,
                current_password=PASSWORD,
                new_password="short",
                current_token=current.token,
            ),
        )


def enable_totp(handlers: IdentityHandlers) -> UUID:
    create(handlers)
    user = handlers.login(Login(email="anna@example.com", password=PASSWORD)).user
    handlers.begin_totp_setup(user.id)
    handlers.confirm_totp(user.id, VALID_TOTP_CODE)
    return user.id


def test_totp_setup_and_login(handlers: IdentityHandlers, store: Store) -> None:
    create(handlers)
    user = handlers.login(Login(email="anna@example.com", password=PASSWORD)).user
    setup = handlers.begin_totp_setup(user.id)
    assert setup.secret == "SECRET"
    assert setup.provisioning_uri == "otpauth://totp/Rhinvoice:anna@example.com?secret=SECRET"
    assert store.users[user.id].totp_pending_secret == "SECRET"
    with raises_exactly(AuthenticationError, "two-factor code is incorrect"):
        handlers.confirm_totp(user.id, "000000")
    assert store.users[user.id].failed_logins == 1
    confirmed = handlers.confirm_totp(user.id, VALID_TOTP_CODE)
    assert confirmed.totp_enabled
    assert confirmed.totp_last_step == TOTP_STEP
    assert store.users[user.id].totp_enabled

    with raises_exactly(TotpRequiredError, "two-factor code required"):
        handlers.login(Login(email="anna@example.com", password=PASSWORD))
    with raises_exactly(TotpRequiredError, "two-factor code required"):
        handlers.login(Login(email="anna@example.com", password=PASSWORD, totp_code=""))
    with raises_exactly(AuthenticationError, "e-mail or password is incorrect"):
        handlers.login(Login(email="anna@example.com", password=PASSWORD, totp_code="999999"))
    # One failed confirmation plus one failed login; only a successful login resets.
    assert store.users[user.id].failed_logins == 2
    result = handlers.login(
        Login(email="anna@example.com", password=PASSWORD, totp_code=NEXT_TOTP_CODE),
    )
    assert result.user.id == user.id
    assert store.users[user.id].failed_logins == 0
    assert store.users[user.id].totp_last_step == TOTP_STEP + 1


def test_totp_codes_cannot_be_replayed(handlers: IdentityHandlers, store: Store) -> None:
    user_id = enable_totp(handlers)
    # The confirmation used step 100; the same code must not log in again.
    with raises_exactly(AuthenticationError, "e-mail or password is incorrect"):
        handlers.login(
            Login(email="anna@example.com", password=PASSWORD, totp_code=VALID_TOTP_CODE)
        )
    handlers.login(Login(email="anna@example.com", password=PASSWORD, totp_code=NEXT_TOTP_CODE))
    with raises_exactly(AuthenticationError, "e-mail or password is incorrect"):
        handlers.login(Login(email="anna@example.com", password=PASSWORD, totp_code=NEXT_TOTP_CODE))
    # The successful login in between reset the counter; the second replay counts again.
    assert store.users[user_id].failed_logins == 1


def test_confirm_totp_without_setup_fails(handlers: IdentityHandlers) -> None:
    create(handlers)
    user = handlers.login(Login(email="anna@example.com", password=PASSWORD)).user
    with raises_exactly(AuthenticationError, "two-factor code is incorrect"):
        handlers.confirm_totp(user.id, VALID_TOTP_CODE)


def test_disable_totp_requires_password_and_code(handlers: IdentityHandlers, store: Store) -> None:
    user_id = enable_totp(handlers)
    with raises_exactly(AuthenticationError, "password is incorrect"):
        handlers.disable_totp(
            DisableTotp(user_id=user_id, password="wrong password", code=NEXT_TOTP_CODE)
        )
    with raises_exactly(AuthenticationError, "two-factor code is incorrect"):
        handlers.disable_totp(DisableTotp(user_id=user_id, password=PASSWORD, code=VALID_TOTP_CODE))
    assert store.users[user_id].totp_enabled
    assert store.users[user_id].failed_logins == 2
    disabled = handlers.disable_totp(
        DisableTotp(user_id=user_id, password=PASSWORD, code=NEXT_TOTP_CODE)
    )
    assert not disabled.totp_enabled
    assert disabled.totp_last_step is None
    assert not store.users[user_id].totp_enabled


def test_disable_totp_when_not_enabled_only_needs_password(handlers: IdentityHandlers) -> None:
    create(handlers)
    user = handlers.login(Login(email="anna@example.com", password=PASSWORD)).user
    disabled = handlers.disable_totp(DisableTotp(user_id=user.id, password=PASSWORD, code=""))
    assert not disabled.totp_enabled


def test_locked_account_is_indistinguishable_without_password(
    handlers: IdentityHandlers,
    hasher: FakePasswordHasher,
) -> None:
    create(handlers)
    for _ in range(5):
        with raises_exactly(AuthenticationError, "e-mail or password is incorrect"):
            handlers.login(Login(email="anna@example.com", password="wrong password"))
    hasher.hashed.clear()
    with raises_exactly(AuthenticationError, "e-mail or password is incorrect") as error:
        handlers.login(Login(email="anna@example.com", password="wrong password"))
    assert error.value.code == "authentication_failed"
    with raises_exactly(AccountLockedError, "too many failed attempts, try again later"):
        handlers.login(Login(email="anna@example.com", password=PASSWORD))


def test_failed_password_checks_count_towards_the_lockout(
    handlers: IdentityHandlers,
    store: Store,
    clock: FixedClock,
) -> None:
    create(handlers)
    session = handlers.login(Login(email="anna@example.com", password=PASSWORD))
    command = ChangePassword(
        user_id=session.user.id,
        current_password="wrong password",
        new_password="another long password",
        current_token=session.token,
    )
    for _ in range(5):
        with raises_exactly(AuthenticationError, "current password is incorrect"):
            handlers.change_password(command)
    assert store.users[session.user.id].locked_until == NOW + timedelta(minutes=15)
    for action in (
        lambda: handlers.change_password(command),
        lambda: handlers.confirm_totp(session.user.id, VALID_TOTP_CODE),
        lambda: handlers.disable_totp(
            DisableTotp(user_id=session.user.id, password=PASSWORD, code=""),
        ),
    ):
        with raises_exactly(AccountLockedError, "too many failed attempts, try again later"):
            action()
    clock.set(NOW + timedelta(minutes=15))
    handlers.change_password(replace(command, current_password=PASSWORD))


def test_login_locks_the_user_row(handlers: IdentityHandlers, store: Store) -> None:
    create(handlers)
    rows: list[int] = []
    handlers_with_spy = replace(handlers, uow=lambda: SpyUnitOfWork(store, rows))
    handlers_with_spy.login(Login(email="anna@example.com", password=PASSWORD))
    assert rows == [1]


def test_sensitive_changes_lock_the_user_row(handlers: IdentityHandlers, store: Store) -> None:
    create(handlers)
    session = handlers.login(Login(email="anna@example.com", password=PASSWORD))
    rows: list[int] = []
    spy = replace(handlers, uow=lambda: SpyUnitOfWork(store, rows))
    spy.change_password(
        ChangePassword(
            user_id=session.user.id,
            current_password=PASSWORD,
            new_password="another long password",
            current_token=session.token,
        ),
    )
    assert rows == [1]
    rows.clear()
    spy.begin_totp_setup(session.user.id)
    assert rows == [0]  # starting the setup changes nothing security relevant


class SpyUnitOfWork(InMemoryUnitOfWork):
    """Records how many rows were read with a lock in each unit of work."""

    def __init__(self, store: Store, rows: list[int]) -> None:
        super().__init__(store)
        self.rows = rows

    def commit(self) -> None:
        self.rows.append(self.users.locked_rows)
        super().commit()


def test_sessions_are_touched_at_most_once_per_minute(
    handlers: IdentityHandlers,
    store: Store,
    clock: FixedClock,
) -> None:
    create(handlers)
    token = handlers.login(Login(email="anna@example.com", password=PASSWORD)).token
    clock.set(NOW + timedelta(seconds=59))
    handlers.authenticate(token)
    assert store.sessions[hash_token(token)].last_seen_at == NOW
    clock.set(NOW + timedelta(seconds=60))
    handlers.authenticate(token)
    assert store.sessions[hash_token(token)].last_seen_at == NOW + timedelta(seconds=60)
