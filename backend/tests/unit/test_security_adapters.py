"""The security adapters are pure library wrappers and are tested for real."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pyotp

from rhinvoice.infrastructure.security import Argon2PasswordHasher, PyOtpTotpService

AT = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def test_argon2_hash_and_verify() -> None:
    hasher = Argon2PasswordHasher()
    password_hash = hasher.hash("correct horse battery")
    assert password_hash.startswith("$argon2id$")
    assert hasher.verify(password_hash, "correct horse battery")
    assert not hasher.verify(password_hash, "wrong")
    assert not hasher.verify("not-a-hash", "correct horse battery")
    assert not hasher.needs_rehash(password_hash)
    weak = "$argon2id$v=19$m=8,t=1,p=1$c29tZXNhbHQ$ZkxPS1EV4T5Gn5w5h3Ew8Q"
    assert hasher.needs_rehash(weak)


def test_totp_matching_step_with_drift_window() -> None:
    service = PyOtpTotpService()
    secret = service.new_secret()
    assert len(secret) == 32
    totp = pyotp.TOTP(secret)
    step = totp.timecode(AT)
    code = totp.at(AT)
    assert service.matching_step(secret, f" {code} ", AT) == step
    assert service.matching_step(secret, code, AT + timedelta(seconds=30)) == step
    assert service.matching_step(secret, code, AT - timedelta(seconds=30)) == step
    assert service.matching_step(secret, code, AT + timedelta(seconds=90)) is None
    wrong = "000000" if code != "000000" else "111111"
    assert service.matching_step(secret, wrong, AT) is None
    assert service.matching_step(secret, totp.at(AT + timedelta(seconds=30)), AT) == step + 1


def test_totp_provisioning_uri() -> None:
    uri = urlparse(PyOtpTotpService().provisioning_uri("JBSWY3DPEHPK3PXP", "anna@example.com"))
    assert uri.scheme == "otpauth"
    assert uri.netloc == "totp"
    assert uri.path == "/Rhinvoice:anna%40example.com"
    assert parse_qs(uri.query) == {"secret": ["JBSWY3DPEHPK3PXP"], "issuer": ["Rhinvoice"]}
