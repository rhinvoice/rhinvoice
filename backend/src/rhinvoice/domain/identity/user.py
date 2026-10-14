"""Users of the installation and their login protection state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.domain.shared.email import EmailAddress

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024
MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION = timedelta(minutes=15)
MAX_DISPLAY_NAME_LENGTH = 200


def validate_password(password: str) -> None:
    """Check a new password against the length policy (NIST SP 800-63B)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            "password",
            f"password must be at least {MIN_PASSWORD_LENGTH} characters long",
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(
            "password",
            f"password must be at most {MAX_PASSWORD_LENGTH} characters long",
        )


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: EmailAddress
    display_name: str
    password_hash: str
    created_at: datetime
    totp_secret: str | None = None
    totp_pending_secret: str | None = None
    failed_logins: int = 0
    locked_until: datetime | None = None
    totp_last_step: int | None = None
    """Last accepted TOTP time step; older or equal steps are replays (RFC 6238 5.2)."""

    def __post_init__(self) -> None:
        name = self.display_name.strip()
        if not name:
            raise ValidationError("display_name", "display name is required")
        if len(name) > MAX_DISPLAY_NAME_LENGTH:
            raise ValidationError(
                "display_name",
                f"display name must be at most {MAX_DISPLAY_NAME_LENGTH} characters long",
            )
        object.__setattr__(self, "display_name", name)

    @property
    def totp_enabled(self) -> bool:
        return self.totp_secret is not None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    def register_failed_login(self, now: datetime) -> User:
        failed = self.failed_logins + 1
        if failed >= MAX_FAILED_LOGINS:
            return replace(self, failed_logins=0, locked_until=now + LOCKOUT_DURATION)
        return replace(self, failed_logins=failed)

    def register_successful_login(self) -> User:
        return replace(self, failed_logins=0, locked_until=None)

    def with_password_hash(self, password_hash: str) -> User:
        return replace(self, password_hash=password_hash)

    def reset_password(self, password_hash: str) -> User:
        """Set a new password after it was forgotten; a lock from failed logins ends with it."""
        return replace(self, password_hash=password_hash, failed_logins=0, locked_until=None)

    def start_totp_setup(self, secret: str) -> User:
        if self.totp_enabled:
            raise InvalidStateError("two-factor authentication is already enabled")
        return replace(self, totp_pending_secret=secret)

    def confirm_totp(self) -> User:
        if self.totp_pending_secret is None:
            raise InvalidStateError("two-factor setup has not been started")
        return replace(self, totp_secret=self.totp_pending_secret, totp_pending_secret=None)

    def disable_totp(self) -> User:
        return replace(self, totp_secret=None, totp_pending_secret=None, totp_last_step=None)

    def accepts_totp_step(self, step: int) -> bool:
        return self.totp_last_step is None or step > self.totp_last_step

    def with_totp_step(self, step: int) -> User:
        return replace(self, totp_last_step=step)
