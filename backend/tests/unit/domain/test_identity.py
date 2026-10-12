from datetime import UTC, datetime, timedelta

import pytest

from rhinvoice.domain.identity.session import (
    ABSOLUTE_TIMEOUT,
    IDLE_TIMEOUT,
    TOUCH_INTERVAL,
    Session,
)
from rhinvoice.domain.identity.user import (
    LOCKOUT_DURATION,
    MAX_FAILED_LOGINS,
    User,
    validate_password,
)
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from tests.helpers import raises_exactly

NOW = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def make_user(**overrides: object) -> User:
    values: dict[str, object] = {
        "id": new_id(),
        "email": EmailAddress("anna@example.com"),
        "display_name": "Anna Muster",
        "password_hash": "hash",
        "created_at": NOW,
    }
    values.update(overrides)
    return User(**values)  # type: ignore[arg-type]  # test factory with dynamic overrides


def test_email_is_normalized_and_validated() -> None:
    assert EmailAddress.parse("  Anna@Example.COM ").value == "anna@example.com"
    assert str(EmailAddress("a@b.example")) == "a@b.example"
    invalid_values = [
        "anna",
        "anna@",
        "@example.com",
        "an na@example.com",
        "a@b",
        "a\x85b@example.com",
        "a@exa\x1fmple.com",
        "a@example.c\ufeffom",
        "a@b@example.com",
    ]
    for invalid in invalid_values:
        with pytest.raises(ValidationError) as error:
            EmailAddress(invalid)
        assert error.value.details == {"email": f"'{invalid}' is not a valid e-mail address"}


def test_email_length_limit() -> None:
    local = "a" * 64
    domain = "b" * (254 - 64 - 1 - 3) + ".ch"
    assert len(EmailAddress(f"{local}@{domain}").value) == 254
    with pytest.raises(ValidationError):
        EmailAddress(f"{local}a@{domain}")


def test_password_policy() -> None:
    validate_password("a" * 12)
    validate_password("a" * 1024)
    with pytest.raises(ValidationError) as short:
        validate_password("a" * 11)
    assert short.value.details == {"password": "password must be at least 12 characters long"}
    with pytest.raises(ValidationError) as long:
        validate_password("a" * 1025)
    assert long.value.details == {"password": "password must be at most 1024 characters long"}


def test_display_name_is_trimmed_and_required() -> None:
    assert make_user(display_name="  Anna  ").display_name == "Anna"
    assert make_user(display_name="x" * 200).display_name == "x" * 200
    with pytest.raises(ValidationError) as empty:
        make_user(display_name="   ")
    assert empty.value.details == {"display_name": "display name is required"}
    with pytest.raises(ValidationError) as long:
        make_user(display_name="x" * 201)
    assert long.value.details == {
        "display_name": "display name must be at most 200 characters long",
    }


def test_user_is_locked_after_too_many_failed_logins() -> None:
    user = make_user()
    for attempt in range(1, MAX_FAILED_LOGINS):
        user = user.register_failed_login(NOW)
        assert user.failed_logins == attempt
        assert not user.is_locked(NOW)
    user = user.register_failed_login(NOW)
    assert user.failed_logins == 0
    assert user.locked_until == NOW + LOCKOUT_DURATION
    assert user.is_locked(NOW + LOCKOUT_DURATION - timedelta(seconds=1))
    assert not user.is_locked(NOW + LOCKOUT_DURATION)
    assert MAX_FAILED_LOGINS == 5
    assert timedelta(minutes=15) == LOCKOUT_DURATION


def test_successful_login_resets_counters() -> None:
    user = make_user(failed_logins=3, locked_until=NOW).register_successful_login()
    assert user.failed_logins == 0
    assert user.locked_until is None


def test_password_hash_can_be_replaced() -> None:
    assert make_user().with_password_hash("new").password_hash == "new"


def test_totp_lifecycle() -> None:
    user = make_user()
    assert not user.totp_enabled
    with raises_exactly(InvalidStateError, "two-factor setup has not been started"):
        user.confirm_totp()
    pending = user.start_totp_setup("S1")
    assert pending.totp_pending_secret == "S1"
    assert not pending.totp_enabled
    enabled = pending.confirm_totp()
    assert enabled.totp_enabled
    assert enabled.totp_secret == "S1"
    assert enabled.totp_pending_secret is None
    with raises_exactly(InvalidStateError, "two-factor authentication is already enabled"):
        enabled.start_totp_setup("S2")
    stepped = enabled.with_totp_step(7)
    assert stepped.totp_last_step == 7
    assert stepped.accepts_totp_step(8)
    assert not stepped.accepts_totp_step(7)
    assert not stepped.accepts_totp_step(6)
    assert enabled.accepts_totp_step(0)
    disabled = stepped.disable_totp()
    assert disabled.totp_last_step is None
    assert disabled.totp_secret is None
    assert disabled.totp_pending_secret is None
    assert pending.disable_totp().totp_pending_secret is None


def test_session_touch_interval() -> None:
    session = Session(token_hash="h", user_id=new_id(), created_at=NOW, last_seen_at=NOW)
    assert not session.needs_touch(NOW + timedelta(seconds=59))
    assert session.needs_touch(NOW + timedelta(seconds=60))
    assert timedelta(minutes=1) == TOUCH_INTERVAL


def test_session_validity_windows() -> None:
    session = Session(token_hash="h", user_id=new_id(), created_at=NOW, last_seen_at=NOW)
    assert session.is_valid(NOW + IDLE_TIMEOUT - timedelta(seconds=1))
    assert not session.is_valid(NOW + IDLE_TIMEOUT)
    late = session.touch(NOW + ABSOLUTE_TIMEOUT - timedelta(seconds=1))
    assert late.last_seen_at == NOW + ABSOLUTE_TIMEOUT - timedelta(seconds=1)
    assert late.is_valid(NOW + ABSOLUTE_TIMEOUT - timedelta(seconds=1))
    assert not late.is_valid(NOW + ABSOLUTE_TIMEOUT)
    assert timedelta(days=7) == IDLE_TIMEOUT
    assert timedelta(days=30) == ABSOLUTE_TIMEOUT
