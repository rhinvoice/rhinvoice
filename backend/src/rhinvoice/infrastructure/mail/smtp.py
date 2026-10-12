"""Sending mails through the company's SMTP server (standard library only)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import TYPE_CHECKING

from rhinvoice.application.errors import DeliveryError
from rhinvoice.domain.mail.server import MailSecurity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rhinvoice.application.mail.ports import OutgoingMail
    from rhinvoice.domain.mail.server import MailServer

TIMEOUT_SECONDS = 30
TOO_LARGE = 552
"""SMTP reply "exceeded storage allocation", the usual answer to a mail over the size limit."""


def message(server: MailServer, mail: OutgoingMail) -> EmailMessage:
    """Build the MIME message: plain text, UTF-8, the files attached."""
    built = EmailMessage()
    built["From"] = formataddr((server.sender_name, str(server.sender)))
    built["To"] = ", ".join(str(address) for address in mail.to)
    if server.reply_to is not None:
        built["Reply-To"] = str(server.reply_to)
    built["Subject"] = mail.subject
    built["Date"] = formatdate(localtime=True)
    built["Message-ID"] = make_msgid(domain=str(server.sender).rsplit("@", 1)[1])
    built.set_content(mail.body)
    for attachment in mail.attachments:
        main, sub = attachment.media_type.split("/", 1)
        built.add_attachment(
            attachment.content, maintype=main, subtype=sub, filename=attachment.name
        )
    return built


class SmtpSender:
    """The mail sender of the application (see MailSender)."""

    def __init__(
        self, timeout: float = TIMEOUT_SECONDS, context: ssl.SSLContext | None = None
    ) -> None:
        self._timeout = timeout
        # Certificates are checked against the system's trust store (tests pass their own).
        self._context = context or ssl.create_default_context()

    def send(self, server: MailServer, mail: OutgoingMail) -> tuple[str, ...]:
        built = message(server, mail)
        to = [str(address) for address in (*mail.to, *mail.bcc)]
        try:
            with self._connect(server) as smtp:
                if server.username:
                    smtp.login(server.username, server.password)
                refused = smtp.send_message(built, from_addr=str(server.sender), to_addrs=to)
        except OSError as error:  # smtplib's and ssl's errors are OSErrors too
            raise _translate(error, server) from None
        return tuple(refused)

    def _connect(self, server: MailServer) -> smtplib.SMTP:
        if server.security is MailSecurity.TLS:
            return smtplib.SMTP_SSL(
                server.host, server.port, timeout=self._timeout, context=self._context
            )
        smtp = smtplib.SMTP(server.host, server.port, timeout=self._timeout)
        try:
            if server.security is MailSecurity.STARTTLS:
                smtp.starttls(context=self._context)
        except BaseException:
            smtp.close()
            raise
        return smtp


def _translate(error: OSError, server: MailServer) -> DeliveryError:  # noqa: PLR0911 - one per case
    """Say in the person's terms what went wrong, with the server's own words."""
    if isinstance(error, smtplib.SMTPResponseException) and error.smtp_code == TOO_LARGE:
        return _error("mail_too_large", "the mail is larger than the server takes", error)
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return _error("mail_auth_failed", "the server refused the user name or password", error)
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return _refused(error.recipients)
    if isinstance(error, smtplib.SMTPSenderRefused):
        return _error(
            "mail_sender_refused", f"the server refused the sender {server.sender}", error
        )
    if isinstance(error, smtplib.SMTPNotSupportedError) and "SMTPUTF8" in str(error):
        return _error(
            "mail_utf8_unsupported",
            "the server takes no addresses with accents or umlauts",
            error,
        )
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return _error(
            "mail_tls_failed",
            "the server does not offer what the settings ask for (STARTTLS or login)",
            error,
        )
    if isinstance(error, ssl.SSLError):
        return _error(
            "mail_tls_failed",
            "the encrypted connection failed (port and encryption must match)",
            error,
        )
    # smtplib turns a read timeout into a lost connection; the cause tells.
    if isinstance(error, TimeoutError) or isinstance(error.__context__, TimeoutError):
        return _error("mail_timeout", "the server did not answer in time", None)
    if isinstance(error, smtplib.SMTPException):
        return _error("mail_failed", "the server did not accept the mail", error)
    return _error("mail_connection_failed", f"no connection to {server.host}:{server.port}", error)


def _refused(recipients: Mapping[str, object]) -> DeliveryError:
    return _error(
        "mail_recipient_refused", f"the server refused the recipient {', '.join(recipients)}", None
    )


def _error(code: str, text: str, cause: BaseException | None) -> DeliveryError:
    """Build the error: the message says what failed, ``details["server"]`` what it said."""
    reason = "" if cause is None else _reason(cause)
    return DeliveryError(text, code=code, details={"server": reason} if reason else None)


def _reason(cause: BaseException) -> str:
    """Return the server's own words, which usually say what is wrong."""
    if isinstance(cause, smtplib.SMTPResponseException):
        said = (
            cause.smtp_error.decode("utf-8", "replace")
            if isinstance(cause.smtp_error, bytes)
            else str(cause.smtp_error)
        )
        return f"{cause.smtp_code} {said.strip()}"
    return str(cause).strip()
