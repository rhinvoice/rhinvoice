"""The outgoing mail server (SMTP) that sends documents to customers.

One per installation, set up in the settings. The password is kept in the
database like the rest of the installation's data (backups are encrypted) and
never leaves the server again: the API only tells whether one is set.
See ADR 0015.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_text

if TYPE_CHECKING:
    from rhinvoice.domain.shared.email import EmailAddress

MAX_HOST = 253
MAX_USERNAME = 254
MAX_PASSWORD = 500
MAX_SENDER_NAME = 120
MIN_PORT = 1
MAX_PORT = 65_535
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class MailSecurity(StrEnum):
    STARTTLS = "starttls"
    """Plain connection upgraded to TLS (usually port 587)."""
    TLS = "tls"
    """TLS from the start (usually port 465)."""
    NONE = "none"
    """No encryption: only for a relay in the own network."""

    @property
    def default_port(self) -> int:
        return {MailSecurity.STARTTLS: 587, MailSecurity.TLS: 465, MailSecurity.NONE: 25}[self]


@dataclass(frozen=True, slots=True)
class MailServer:
    host: str
    port: int
    security: MailSecurity
    sender: EmailAddress
    """The From address; many providers only accept their own addresses."""
    sender_name: str = ""
    username: str = ""
    """Empty: the server takes mail without login (a relay in the own network)."""
    password: str = field(default="", repr=False)
    """Never printed: tracebacks and logs show the server without it."""
    reply_to: EmailAddress | None = None
    copy_to_sender: bool = True
    """Send a blind copy of every mail to the sender address, as a record."""

    def __post_init__(self) -> None:
        host = clean_text(self.host, "host", max_length=MAX_HOST, required=True)
        if any(character.isspace() or character in "/@:" for character in host):
            raise ValidationError(
                "host", "the server is a host name or IP address, e.g. smtp.example.com"
            )
        object.__setattr__(self, "host", host)
        if not MIN_PORT <= self.port <= MAX_PORT:
            raise ValidationError("port", f"the port must be between {MIN_PORT} and {MAX_PORT}")
        object.__setattr__(
            self,
            "sender_name",
            clean_text(self.sender_name, "sender_name", max_length=MAX_SENDER_NAME),
        )
        object.__setattr__(
            self, "username", clean_text(self.username, "username", max_length=MAX_USERNAME)
        )
        # Passwords keep their spaces; control characters never belong in one.
        if len(self.password) > MAX_PASSWORD or _CONTROL.search(self.password):
            raise ValidationError(
                "password", "the password is too long or contains control characters"
            )
        if self.password and not self.username:
            raise ValidationError("username", "a password needs a user name")
        if self.username and self.security is MailSecurity.NONE:
            # The login would cross the network in plain text.
            raise ValidationError(
                "security", "a login needs an encrypted connection", code="mail_login_needs_tls"
            )
