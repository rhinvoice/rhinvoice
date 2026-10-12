"""Use cases around users, login sessions and two-factor authentication."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, NoReturn

from rhinvoice.application.errors import (
    AccountLockedError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    TotpRequiredError,
)
from rhinvoice.domain.identity.session import Session
from rhinvoice.domain.identity.user import User, validate_password
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id

if TYPE_CHECKING:
    from uuid import UUID

    from rhinvoice.application.identity.ports import PasswordHasher, TotpService
    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.shared.clock import Clock

INVALID_CREDENTIALS = "e-mail or password is incorrect"
INVALID_TOTP = "two-factor code is incorrect"
SESSION_TOKEN_BYTES = 48


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CreateUser:
    email: str
    display_name: str
    password: str


@dataclass(frozen=True, slots=True)
class Login:
    email: str
    password: str
    totp_code: str | None = None


@dataclass(frozen=True, slots=True)
class LoginResult:
    token: str
    user: User


@dataclass(frozen=True, slots=True)
class ChangePassword:
    user_id: UUID
    current_password: str
    new_password: str
    current_token: str


@dataclass(frozen=True, slots=True)
class DisableTotp:
    user_id: UUID
    password: str
    code: str


@dataclass(frozen=True, slots=True)
class TotpSetup:
    secret: str
    provisioning_uri: str


@dataclass(frozen=True, slots=True)
class IdentityHandlers:
    uow: UnitOfWorkFactory
    hasher: PasswordHasher
    totp: TotpService
    clock: Clock
    lockout: bool = True
    """Lock an account after repeated failed logins; off only for a public demo."""

    def create_user(self, command: CreateUser) -> User:
        with self.uow() as uow:
            user = self._add_user(uow, command)
            uow.commit()
        return user

    def create_first_user(self, command: CreateUser) -> User:
        """Create the initial user; refused as soon as any user exists."""
        with self.uow() as uow:
            uow.users.lock()
            if uow.users.count() > 0:
                raise ConflictError("setup has already been completed")
            user = self._add_user(uow, command)
            uow.commit()
        return user

    def _add_user(self, uow: UnitOfWork, command: CreateUser) -> User:
        email = EmailAddress.parse(command.email)
        validate_password(command.password)
        if uow.users.get_by_email(email) is not None:
            raise ConflictError(f"a user with e-mail {email} already exists")
        user = User(
            id=new_id(),
            email=email,
            display_name=command.display_name,
            password_hash=self.hasher.hash(command.password),
            created_at=self.clock.now(),
        )
        uow.users.add(user)
        return user

    def has_users(self) -> bool:
        with self.uow() as uow:
            return uow.users.count() > 0

    def login(self, command: Login) -> LoginResult:
        now = self.clock.now()
        with self.uow() as uow:
            # The row lock serialises concurrent attempts so that none of them is lost.
            user = self._find_by_email(uow, command.email)
            if user is None:
                # Spend the same time as for an existing user to avoid user enumeration.
                self.hasher.hash(command.password)
                raise AuthenticationError(INVALID_CREDENTIALS)
            password_ok = self.hasher.verify(user.password_hash, command.password)
            if user.is_locked(now):
                # Only someone who knows the password learns that the account is locked.
                if password_ok:
                    raise AccountLockedError("too many failed attempts, try again later")
                raise AuthenticationError(INVALID_CREDENTIALS)
            if not password_ok:
                self._fail(uow, user, INVALID_CREDENTIALS)
            if user.totp_secret is not None:
                if not command.totp_code:
                    raise TotpRequiredError("two-factor code required")
                user = self._consume_totp(
                    uow,
                    user,
                    user.totp_secret,
                    command.totp_code,
                    INVALID_CREDENTIALS,
                )
            user = user.register_successful_login()
            if self.hasher.needs_rehash(user.password_hash):
                user = user.with_password_hash(self.hasher.hash(command.password))
            uow.users.update(user)
            token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
            uow.sessions.add(
                Session(
                    token_hash=hash_token(token),
                    user_id=user.id,
                    created_at=now,
                    last_seen_at=now,
                ),
            )
            uow.commit()
        return LoginResult(token=token, user=user)

    @staticmethod
    def _find_by_email(uow: UnitOfWork, raw_email: str) -> User | None:
        try:
            email = EmailAddress.parse(raw_email)
        except ValidationError:
            return None
        return uow.users.get_by_email(email, for_update=True)

    def _fail(self, uow: UnitOfWork, user: User, message: str) -> NoReturn:
        """Count a failed attempt (towards the lockout), persist it and reject."""
        if self.lockout:
            uow.users.update(user.register_failed_login(self.clock.now()))
            uow.commit()
        raise AuthenticationError(message)

    def _consume_totp(
        self,
        uow: UnitOfWork,
        user: User,
        secret: str,
        code: str,
        message: str,
    ) -> User:
        """Accept a TOTP code once; replays and wrong codes count as failures."""
        step = self.totp.matching_step(secret, code, self.clock.now())
        if step is None or not user.accepts_totp_step(step):
            self._fail(uow, user, message)
        return user.with_totp_step(step)

    def _locked_user(self, uow: UnitOfWork, user_id: UUID) -> User:
        user = self._require_user(uow, user_id, for_update=True)
        if user.is_locked(self.clock.now()):
            raise AccountLockedError("too many failed attempts, try again later")
        return user

    def authenticate(self, token: str) -> User | None:
        now = self.clock.now()
        with self.uow() as uow:
            token_hash = hash_token(token)
            session = uow.sessions.get(token_hash)
            if session is None:
                return None
            user = uow.users.get(session.user_id)
            if user is None or not session.is_valid(now):
                uow.sessions.delete(token_hash)
                uow.commit()
                return None
            if session.needs_touch(now):
                uow.sessions.update(session.touch(now))
                uow.commit()
        return user

    def logout(self, token: str) -> None:
        with self.uow() as uow:
            uow.sessions.delete(hash_token(token))
            uow.commit()

    def get_user(self, user_id: UUID) -> User:
        with self.uow() as uow:
            return self._require_user(uow, user_id)

    def change_password(self, command: ChangePassword) -> None:
        validate_password(command.new_password)
        with self.uow() as uow:
            user = self._locked_user(uow, command.user_id)
            if not self.hasher.verify(user.password_hash, command.current_password):
                self._fail(uow, user, "current password is incorrect")
            uow.users.update(user.with_password_hash(self.hasher.hash(command.new_password)))
            uow.sessions.delete_for_user(
                user.id,
                except_token_hash=hash_token(command.current_token),
            )
            uow.commit()

    def begin_totp_setup(self, user_id: UUID) -> TotpSetup:
        secret = self.totp.new_secret()
        with self.uow() as uow:
            user = self._require_user(uow, user_id).start_totp_setup(secret)
            uow.users.update(user)
            uow.commit()
        return TotpSetup(
            secret=secret,
            provisioning_uri=self.totp.provisioning_uri(secret, str(user.email)),
        )

    def confirm_totp(self, user_id: UUID, code: str) -> User:
        with self.uow() as uow:
            user = self._locked_user(uow, user_id)
            pending = user.totp_pending_secret
            if pending is None:
                raise AuthenticationError(INVALID_TOTP)
            user = self._consume_totp(uow, user, pending, code, INVALID_TOTP).confirm_totp()
            uow.users.update(user)
            uow.commit()
        return user

    def disable_totp(self, command: DisableTotp) -> User:
        """Turn off 2FA; requires the password and a current code."""
        with self.uow() as uow:
            user = self._locked_user(uow, command.user_id)
            if not self.hasher.verify(user.password_hash, command.password):
                self._fail(uow, user, "password is incorrect")
            if user.totp_secret is not None:
                user = self._consume_totp(uow, user, user.totp_secret, command.code, INVALID_TOTP)
            user = user.disable_totp()
            uow.users.update(user)
            uow.commit()
        return user

    @staticmethod
    def _require_user(uow: UnitOfWork, user_id: UUID, *, for_update: bool = False) -> User:
        user = uow.users.get(user_id, for_update=for_update)
        if user is None:
            raise NotFoundError("user not found")
        return user
