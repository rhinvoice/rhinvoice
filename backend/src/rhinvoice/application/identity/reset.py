"""A forgotten password, reset with a one-time code that only this computer's user can read.

The installation without Docker writes the code into its private data folder (ADR 0024): whoever
can open that folder can read all data anyway. On a server there is no such place the browser's
user owns, so there an administrator resets the password with the command line.
"""

from __future__ import annotations

import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.application.identity.handlers import ResetPassword
from rhinvoice.domain.identity.user import validate_password

if TYPE_CHECKING:
    from collections.abc import Callable

    from rhinvoice.application.identity.handlers import IdentityHandlers
    from rhinvoice.domain.shared.clock import Clock

CODE_VALIDITY = timedelta(minutes=15)
MAX_ATTEMPTS = 5
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
"""Without 0, 1, I and O, which are easily mistaken for each other."""
CODE_GROUP = 5
INVALID_CODE = "the e-mail address or the code is not valid"


class ResetDelivery(Protocol):
    """Hands the code to the computer's user, never to the browser."""

    def deliver(self, code: str, accounts: list[str], valid_until: datetime) -> None: ...
    def remove(self) -> None: ...


class ResetMethod(StrEnum):
    FILE = "file"
    ADMINISTRATOR = "administrator"


@dataclass(frozen=True, slots=True)
class ConfirmReset:
    email: str
    code: str
    new_password: str


@dataclass(slots=True)
class _Pending:
    code: str
    valid_until: datetime
    attempts: int = 0


def new_code() -> str:
    letters = "".join(secrets.choice(CODE_ALPHABET) for _ in range(2 * CODE_GROUP))
    return f"{letters[:CODE_GROUP]}-{letters[CODE_GROUP:]}"


def _normalized(code: str) -> str:
    return "".join(code.split()).replace("-", "").upper()


class PasswordReset:
    """Holds at most one code, in memory: a restart of the program voids it."""

    def __init__(
        self,
        identity: IdentityHandlers,
        delivery: ResetDelivery | None,
        clock: Clock,
        *,
        codes: Callable[[], str] = new_code,
    ) -> None:
        self._identity = identity
        self._delivery = delivery
        self._clock = clock
        self._codes = codes
        self._pending: _Pending | None = None
        self._lock = threading.Lock()

    @property
    def method(self) -> ResetMethod:
        return ResetMethod.ADMINISTRATOR if self._delivery is None else ResetMethod.FILE

    def request(self) -> None:
        """Make a new code (the old one ends) and deliver it with the accounts' addresses."""
        if self._delivery is None:
            raise ConflictError(
                "an administrator resets the password on the server",
                code="reset_by_administrator",
            )
        accounts = [account.email for account in self._identity.accounts()]
        with self._lock:
            code = self._codes()
            self._pending = _Pending(_normalized(code), self._clock.now() + CODE_VALIDITY)
            self._delivery.deliver(code, accounts, self._pending.valid_until)

    def confirm(self, command: ConfirmReset) -> None:
        validate_password(command.new_password)
        with self._lock:
            pending = self._pending
            if pending is None or self._clock.now() >= pending.valid_until:
                self._void()
                raise _invalid()
            if hmac.compare_digest(pending.code, _normalized(command.code)):
                try:
                    self._identity.reset_password(
                        ResetPassword(command.email, command.new_password)
                    )
                except NotFoundError:
                    pass
                else:
                    self._void()
                    return
            # A wrong code and an unknown address look alike and both cost a try.
            pending.attempts += 1
            if pending.attempts >= MAX_ATTEMPTS:
                self._void()
            raise _invalid()

    def _void(self) -> None:
        if self._pending is not None and self._delivery is not None:
            self._delivery.remove()
        self._pending = None


def _invalid() -> ConflictError:
    return ConflictError(INVALID_CODE, code="reset_code_invalid")
