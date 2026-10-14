"""A forgotten password: reset by the admin, or with a code only this computer's user sees."""

from datetime import UTC, datetime, timedelta

import pytest

from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.application.identity.handlers import (
    Account,
    CreateUser,
    IdentityHandlers,
    Login,
    ResetPassword,
)
from rhinvoice.application.identity.reset import (
    CODE_VALIDITY,
    MAX_ATTEMPTS,
    ConfirmReset,
    PasswordReset,
    ResetMethod,
    new_code,
)
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import ValidationError
from tests.helpers import raises_exactly
from tests.unit.application.fakes import (
    FakePasswordHasher,
    FakeTotpService,
    InMemoryUnitOfWork,
    Store,
)

PASSWORD = "correct horse battery"
NEW_PASSWORD = "a new and long passphrase"
NOW = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
CODE = "K7QM2-XWP9D"
INVALID = "the e-mail address or the code is not valid"


class Delivery:
    """Stands in for the file in the data folder of the installation without Docker."""

    def __init__(self) -> None:
        self.delivered: list[tuple[str, list[str], datetime]] = []
        self.removed = 0

    def deliver(self, code: str, accounts: list[str], valid_until: datetime) -> None:
        self.delivered.append((code, accounts, valid_until))

    def remove(self) -> None:
        self.removed += 1


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def identity(store: Store, clock: FixedClock) -> IdentityHandlers:
    handlers = IdentityHandlers(
        uow=lambda: InMemoryUnitOfWork(store),
        hasher=FakePasswordHasher(),
        totp=FakeTotpService(),
        clock=clock,
    )
    for email in ("zora@example.com", "anna@example.com"):
        handlers.create_user(CreateUser(email=email, display_name="Anna", password=PASSWORD))
    return handlers


@pytest.fixture
def delivery() -> Delivery:
    return Delivery()


@pytest.fixture
def reset(identity: IdentityHandlers, delivery: Delivery, clock: FixedClock) -> PasswordReset:
    return PasswordReset(identity, delivery, clock, codes=lambda: CODE)


def logs_in(identity: IdentityHandlers, password: str, email: str = "anna@example.com") -> bool:
    try:
        identity.login(Login(email=email, password=password))
    except Exception:  # noqa: BLE001 - any refusal
        return False
    return True


def test_the_accounts_are_listed_by_e_mail_address(identity: IdentityHandlers) -> None:
    assert identity.accounts() == [
        Account("anna@example.com", "Anna"),
        Account("zora@example.com", "Anna"),
    ]


def test_the_administrator_sets_a_new_password(identity: IdentityHandlers, store: Store) -> None:
    session = identity.login(Login(email="anna@example.com", password=PASSWORD))
    identity.reset_password(ResetPassword(email=" Anna@Example.com ", new_password=NEW_PASSWORD))
    assert logs_in(identity, NEW_PASSWORD)
    assert not logs_in(identity, PASSWORD)
    # Every session of the account ends: someone may have used the old password.
    assert identity.authenticate(session.token) is None
    assert len(store.sessions) == 1  # the login with the new password


def test_a_reset_lifts_the_lock_of_failed_logins(identity: IdentityHandlers) -> None:
    for _ in range(5):
        logs_in(identity, "wrong")
    assert not logs_in(identity, PASSWORD)  # locked
    identity.reset_password(ResetPassword(email="anna@example.com", new_password=NEW_PASSWORD))
    assert logs_in(identity, NEW_PASSWORD)


def test_the_administrator_needs_an_existing_account_and_a_good_password(
    identity: IdentityHandlers,
) -> None:
    with raises_exactly(NotFoundError, "no user with e-mail nobody@example.com"):
        identity.reset_password(
            ResetPassword(email="nobody@example.com", new_password=NEW_PASSWORD)
        )
    with pytest.raises(ValidationError):
        identity.reset_password(ResetPassword(email="anna@example.com", new_password="short"))


def test_without_a_delivery_the_administrator_resets_it(
    identity: IdentityHandlers, clock: FixedClock
) -> None:
    server = PasswordReset(identity, None, clock)
    assert server.method is ResetMethod.ADMINISTRATOR
    with raises_exactly(
        ConflictError, "an administrator resets the password on the server"
    ) as refused:
        server.request()
    assert refused.value.code == "reset_by_administrator"
    with raises_exactly(ConflictError, INVALID):
        server.confirm(ConfirmReset("anna@example.com", CODE, NEW_PASSWORD))


def test_a_code_is_delivered_with_the_accounts_and_resets_once(
    reset: PasswordReset, delivery: Delivery, identity: IdentityHandlers
) -> None:
    assert reset.method is ResetMethod.FILE
    reset.request()
    assert delivery.delivered == [
        (CODE, ["anna@example.com", "zora@example.com"], NOW + CODE_VALIDITY)
    ]
    # Typed as it comes: lower case, spaces, without the dash.
    reset.confirm(ConfirmReset("anna@example.com", " k7qm2 xwp9d ", NEW_PASSWORD))
    assert logs_in(identity, NEW_PASSWORD)
    assert delivery.removed == 1
    with raises_exactly(ConflictError, INVALID) as reused:
        reset.confirm(ConfirmReset("anna@example.com", CODE, PASSWORD))
    assert reused.value.code == "reset_code_invalid"


def test_a_code_is_valid_for_a_quarter_of_an_hour(reset: PasswordReset, clock: FixedClock) -> None:
    reset.request()
    clock.set(NOW + CODE_VALIDITY)
    with raises_exactly(ConflictError, INVALID):
        reset.confirm(ConfirmReset("anna@example.com", CODE, NEW_PASSWORD))
    assert timedelta(minutes=15) == CODE_VALIDITY
    assert MAX_ATTEMPTS == 5


def test_a_code_works_until_its_last_second(
    reset: PasswordReset, clock: FixedClock, identity: IdentityHandlers
) -> None:
    reset.request()
    clock.set(NOW + CODE_VALIDITY - timedelta(seconds=1))
    reset.confirm(ConfirmReset("anna@example.com", CODE, NEW_PASSWORD))
    assert logs_in(identity, NEW_PASSWORD)


def test_a_code_is_void_after_too_many_wrong_tries(
    reset: PasswordReset, delivery: Delivery
) -> None:
    reset.request()
    for _ in range(MAX_ATTEMPTS):
        with raises_exactly(ConflictError, INVALID):
            reset.confirm(ConfirmReset("anna@example.com", "WRONG-CODE0", NEW_PASSWORD))
    assert delivery.removed == 1  # the void code's file goes too
    with raises_exactly(ConflictError, INVALID):
        reset.confirm(ConfirmReset("anna@example.com", CODE, NEW_PASSWORD))


def test_wrong_tries_below_the_limit_keep_the_code(
    reset: PasswordReset, delivery: Delivery
) -> None:
    reset.request()
    for _ in range(MAX_ATTEMPTS - 1):
        with raises_exactly(ConflictError, INVALID):
            reset.confirm(ConfirmReset("anna@example.com", "WRONG-CODE0", NEW_PASSWORD))
    assert delivery.removed == 0
    reset.confirm(ConfirmReset("anna@example.com", CODE, NEW_PASSWORD))


def test_an_unknown_account_gets_no_hint_but_costs_a_try(reset: PasswordReset) -> None:
    reset.request()
    for _ in range(MAX_ATTEMPTS):
        with raises_exactly(ConflictError, INVALID):
            reset.confirm(ConfirmReset("nobody@example.com", CODE, NEW_PASSWORD))
    with raises_exactly(ConflictError, INVALID):
        reset.confirm(ConfirmReset("not an address", CODE, NEW_PASSWORD))
    with raises_exactly(ConflictError, INVALID):
        reset.confirm(ConfirmReset("anna@example.com", CODE, NEW_PASSWORD))


def test_a_weak_password_is_refused_before_the_code_is_tried(reset: PasswordReset) -> None:
    reset.request()
    for _ in range(MAX_ATTEMPTS + 1):
        with pytest.raises(ValidationError):
            reset.confirm(ConfirmReset("anna@example.com", CODE, "short"))
    reset.confirm(ConfirmReset("anna@example.com", CODE, NEW_PASSWORD))


def test_a_new_request_replaces_the_code(
    reset: PasswordReset, delivery: Delivery, identity: IdentityHandlers, clock: FixedClock
) -> None:
    codes = iter(["AAAAA-AAAAA", "BBBBB-BBBBB"])
    renewing = PasswordReset(identity, delivery, clock, codes=lambda: next(codes))
    renewing.request()
    renewing.request()
    with raises_exactly(ConflictError, INVALID):
        renewing.confirm(ConfirmReset("anna@example.com", "AAAAA-AAAAA", NEW_PASSWORD))
    renewing.confirm(ConfirmReset("anna@example.com", "BBBBB-BBBBB", NEW_PASSWORD))
    del reset


def test_codes_are_random_and_easy_to_type() -> None:
    codes = {new_code() for _ in range(50)}
    assert len(codes) == 50
    for code in codes:
        first, second = code.split("-")
        assert len(first) == len(second) == 5
        # No letters that look like digits.
        assert not set(first + second) & set("01IO")
        assert (first + second).isalnum()
        assert (first + second).isupper() or (first + second).isdigit()


def test_without_a_requested_code_there_is_nothing_to_confirm(
    reset: PasswordReset, delivery: Delivery
) -> None:
    with raises_exactly(ConflictError, INVALID):
        reset.confirm(ConfirmReset("anna@example.com", CODE, NEW_PASSWORD))
    assert delivery.removed == 0  # no file of this program to remove
