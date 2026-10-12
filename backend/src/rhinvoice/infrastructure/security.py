"""Password hashing (argon2id) and TOTP (RFC 6238) adapters."""

import hmac
import threading
from datetime import datetime

import pyotp
from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError

ISSUER = "Rhinvoice"


MAX_CONCURRENT_HASHES = 2
"""Each argon2 run takes 64 MiB; a burst of logins waits instead of exhausting memory."""


class Argon2PasswordHasher:
    """argon2id with the library's RFC 9106 low-memory defaults."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_HASHES) -> None:
        self._hasher = Argon2Hasher()
        self._slots = threading.BoundedSemaphore(max_concurrent)

    def hash(self, password: str) -> str:
        with self._slots:
            return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        with self._slots:
            try:
                return self._hasher.verify(password_hash, password)
            except (VerificationError, InvalidHashError):
                return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)


class PyOtpTotpService:
    def new_secret(self) -> str:
        return pyotp.random_base32()

    def matching_step(self, secret: str, code: str, at: datetime) -> int | None:
        """Accept the current step and one step on each side (clock drift)."""
        totp = pyotp.TOTP(secret)
        candidate = code.strip()
        current = totp.timecode(at)
        for step in (current - 1, current, current + 1):
            if hmac.compare_digest(totp.generate_otp(step), candidate):
                return step
        return None

    def provisioning_uri(self, secret: str, account: str) -> str:
        totp = pyotp.TOTP(secret)
        # pyotp declares **kwargs without a type; the call itself is fully typed.
        return totp.provisioning_uri(name=account, issuer_name=ISSUER)  # pyright: ignore[reportUnknownMemberType]
