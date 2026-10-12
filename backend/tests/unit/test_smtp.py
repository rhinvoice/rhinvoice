# ruff: noqa: RUF001 - mails use typographic dashes.
"""The SMTP adapter against a real local mail server (aiosmtpd)."""

import email
import socket
import ssl
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.policy import default as default_policy

import pytest
import trustme
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, Envelope, LoginPassword, Session

from rhinvoice.application.errors import DeliveryError
from rhinvoice.application.mail.ports import Attachment, OutgoingMail
from rhinvoice.domain.mail.server import MailSecurity, MailServer
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.infrastructure.mail.smtp import SmtpSender, message
from tests.helpers import raises_exactly

HOST = "127.0.0.1"
SENDER = EmailAddress("rechnung@muster.example")
TO = EmailAddress("buchhaltung@kunde.example")
MAIL = OutgoingMail(
    to=(TO,),
    subject="Rechnung R20260001 – Muster & Söhne",
    body="Guten Tag\n\nIm Anhang die Rechnung.\n\nFreundliche Grüsse",
    attachments=(
        Attachment("Rechnung R20260001.pdf", b"%PDF-1.7 test", "application/pdf"),
        Attachment("XRechnung R20260001.xml", b"<x/>", "application/xml"),
    ),
    bcc=(SENDER,),
)


@dataclass
class Inbox:
    envelopes: list[Envelope] = field(default_factory=list[Envelope])
    refuse: str | None = None

    async def handle_RCPT(  # noqa: N802 - aiosmtpd hook name
        self, server: object, session: Session, envelope: Envelope, address: str, options: list[str]
    ) -> str:
        del server, session, options
        if address == self.refuse:
            return "550 5.1.1 mailbox unavailable"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(  # noqa: N802 - aiosmtpd hook name
        self, server: object, session: Session, envelope: Envelope
    ) -> str:
        del server, session
        self.envelopes.append(envelope)
        return "250 Message accepted"

    def parsed(self) -> EmailMessage:
        content = self.envelopes[-1].content
        assert isinstance(content, bytes)
        parsed = email.message_from_bytes(content, policy=default_policy)
        assert isinstance(parsed, EmailMessage)
        return parsed


def authenticate(
    server: object, session: Session, envelope: Envelope, mechanism: str, data: object
) -> AuthResult:
    del server, session, envelope, mechanism
    ok = isinstance(data, LoginPassword) and (data.login, data.password) == (b"rechnung", b"geheim")
    return AuthResult(success=ok, handled=False)


@pytest.fixture(scope="module")
def ca() -> trustme.CA:
    return trustme.CA()


@pytest.fixture(scope="module")
def server_context(ca: trustme.CA) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    # trustme also accepts pyOpenSSL contexts, which have no type information.
    ca.issue_cert(HOST).configure_cert(context)  # pyright: ignore[reportUnknownMemberType]
    return context


@pytest.fixture
def client_context(ca: trustme.CA) -> ssl.SSLContext:
    context = ssl.create_default_context()
    ca.configure_trust(context)  # pyright: ignore[reportUnknownMemberType] - see above
    return context


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def start(controller: Controller) -> Iterator[Controller]:
    controller.start()
    try:
        yield controller
    finally:
        controller.stop()


@pytest.fixture
def inbox() -> Inbox:
    return Inbox()


@pytest.fixture
def starttls(inbox: Inbox, server_context: ssl.SSLContext) -> Iterator[Controller]:
    yield from start(
        Controller(
            inbox,
            hostname=HOST,
            port=free_port(),
            tls_context=server_context,
            require_starttls=True,
            authenticator=authenticate,
            auth_require_tls=True,
            # One mechanism: smtplib would try the next one after a refused login.
            auth_exclude_mechanism=["LOGIN"],
        )
    )


@pytest.fixture
def implicit_tls(inbox: Inbox, server_context: ssl.SSLContext) -> Iterator[Controller]:
    yield from start(
        Controller(
            inbox,
            hostname=HOST,
            port=free_port(),
            ssl_context=server_context,
            authenticator=authenticate,
            auth_require_tls=False,
        )
    )


@pytest.fixture
def plain(inbox: Inbox) -> Iterator[Controller]:
    yield from start(Controller(inbox, hostname=HOST, port=free_port()))


def port_of(controller: Controller) -> int:
    return int(controller.port)


def settings(controller: Controller, security: MailSecurity, **overrides: object) -> MailServer:
    values: dict[str, object] = {
        "host": HOST,
        "port": port_of(controller),
        "security": security,
        "sender": SENDER,
        "sender_name": "Muster & Söhne GmbH",
        "username": "rechnung",
        "password": "geheim",
    }
    values.update(overrides)
    return MailServer(**values)  # type: ignore[arg-type]  # test builder


def test_a_mail_over_starttls_with_login(
    starttls: Controller, inbox: Inbox, client_context: ssl.SSLContext
) -> None:
    SmtpSender(context=client_context).send(
        settings(starttls, MailSecurity.STARTTLS, reply_to=EmailAddress("info@muster.example")),
        MAIL,
    )
    [envelope] = inbox.envelopes
    assert envelope.mail_from == str(SENDER)
    # The blind copy is delivered but named in no header.
    assert envelope.rcpt_tos == [str(TO), str(SENDER)]
    received = inbox.parsed()
    assert received["From"] == "Muster & Söhne GmbH <rechnung@muster.example>"
    assert received["To"] == "buchhaltung@kunde.example"
    assert received["Bcc"] is None
    assert received["Reply-To"] == "info@muster.example"
    assert received["Subject"] == "Rechnung R20260001 – Muster & Söhne"
    assert received["Message-ID"].endswith("@muster.example>")
    assert received["Date"]
    body = received.get_body(("plain",))
    assert body is not None
    assert (
        body.get_content().replace("\r\n", "\n")
        == "Guten Tag\n\nIm Anhang die Rechnung.\n\nFreundliche Grüsse\n"
    )
    attachments = [
        (part.get_filename(), part.get_content_type(), part.get_content())
        for part in received.iter_attachments()
    ]
    assert attachments == [
        ("Rechnung R20260001.pdf", "application/pdf", b"%PDF-1.7 test"),
        ("XRechnung R20260001.xml", "application/xml", b"<x/>"),
    ]


def test_a_mail_over_tls(
    implicit_tls: Controller, inbox: Inbox, client_context: ssl.SSLContext
) -> None:
    SmtpSender(context=client_context).send(settings(implicit_tls, MailSecurity.TLS), MAIL)
    assert len(inbox.envelopes) == 1


def test_a_relay_without_encryption_and_login(plain: Controller, inbox: Inbox) -> None:
    server = settings(plain, MailSecurity.NONE, username="", password="", sender_name="")
    SmtpSender().send(server, OutgoingMail(to=(TO,), subject="Test", body="Hallo"))
    received = inbox.parsed()
    assert received["From"] == "rechnung@muster.example"
    assert received["Reply-To"] is None
    assert list(received.iter_attachments()) == []


def test_a_wrong_password(starttls: Controller, client_context: ssl.SSLContext) -> None:
    with raises_exactly(DeliveryError, "the server refused the user name or password") as error:
        SmtpSender(context=client_context).send(
            settings(starttls, MailSecurity.STARTTLS, password="falsch"), MAIL
        )
    assert error.value.code == "mail_auth_failed"
    assert error.value.details == {"server": "535 5.7.8 Authentication credentials invalid"}


def test_a_refused_recipient(plain: Controller, inbox: Inbox) -> None:
    inbox.refuse = str(TO)
    # The customer refused, the blind copy taken: the caller learns whom the server refused.
    assert SmtpSender().send(
        settings(plain, MailSecurity.NONE, username="", password=""), MAIL
    ) == (str(TO),)
    # The only recipient refused: nothing went out.
    with raises_exactly(
        DeliveryError, "the server refused the recipient buchhaltung@kunde.example"
    ) as alone:
        SmtpSender().send(
            settings(plain, MailSecurity.NONE, username="", password=""),
            OutgoingMail(to=(TO,), subject="x", body="y"),
        )
    assert alone.value.code == "mail_recipient_refused"
    # One of several refused: the others get the mail, the refused ones are named.
    refused = SmtpSender().send(
        settings(plain, MailSecurity.NONE, username="", password=""),
        OutgoingMail(to=(SENDER, TO), subject="x", body="y"),
    )
    assert refused == (str(TO),)
    assert inbox.envelopes[-1].rcpt_tos == [str(SENDER)]


def test_starttls_against_a_server_without_it(plain: Controller) -> None:
    with raises_exactly(
        DeliveryError, "the server does not offer what the settings ask for (STARTTLS or login)"
    ) as error:
        SmtpSender().send(settings(plain, MailSecurity.STARTTLS), MAIL)
    assert error.value.code == "mail_tls_failed"


def test_tls_against_a_plain_server(plain: Controller) -> None:
    with pytest.raises(DeliveryError) as error:
        SmtpSender(timeout=5).send(settings(plain, MailSecurity.TLS), MAIL)
    assert error.value.code == "mail_tls_failed"
    assert error.value.message == "the encrypted connection failed (port and encryption must match)"
    assert error.value.details["server"]


def test_an_untrusted_certificate(starttls: Controller) -> None:
    # The system's trust store does not know the test CA.
    with pytest.raises(DeliveryError) as error:
        SmtpSender().send(settings(starttls, MailSecurity.STARTTLS), MAIL)
    assert error.value.code == "mail_tls_failed"
    assert "CERTIFICATE_VERIFY_FAILED" in error.value.details["server"]


def test_nobody_listening() -> None:
    port = free_port()
    server = MailServer(host=HOST, port=port, security=MailSecurity.NONE, sender=SENDER)
    with pytest.raises(DeliveryError) as error:
        SmtpSender().send(server, MAIL)
    assert error.value.code == "mail_connection_failed"
    assert error.value.message == f"no connection to {HOST}:{port}"
    assert error.value.details["server"]


def test_a_server_that_does_not_answer() -> None:
    with socket.socket() as silent:
        silent.bind((HOST, 0))
        silent.listen()
        port = silent.getsockname()[1]
        server = MailServer(host=HOST, port=port, security=MailSecurity.NONE, sender=SENDER)
        with raises_exactly(DeliveryError, "the server did not answer in time") as error:
            SmtpSender(timeout=0.3).send(server, MAIL)
    assert error.value.code == "mail_timeout"


def test_a_server_that_hangs_up() -> None:
    with socket.socket() as rude:
        rude.bind((HOST, 0))
        rude.listen()
        port = rude.getsockname()[1]

        def hang_up() -> None:
            connection, _ = rude.accept()
            connection.sendall(b"554 no service\r\n")
            connection.close()

        thread = threading.Thread(target=hang_up)
        thread.start()
        server = MailServer(host=HOST, port=port, security=MailSecurity.NONE, sender=SENDER)
        with pytest.raises(DeliveryError) as error:
            SmtpSender(timeout=5).send(server, MAIL)
        thread.join()
    assert error.value.code == "mail_failed"
    assert error.value.message == "the server did not accept the mail"
    assert error.value.details == {"server": "554 no service"}


def test_a_refused_sender(plain: Controller, inbox: Inbox) -> None:
    async def refuse_sender(
        server: object, session: Session, envelope: Envelope, address: str, options: list[str]
    ) -> str:
        del server, session, envelope, address, options
        return "553 5.7.1 sender not allowed"

    inbox.handle_MAIL = refuse_sender  # type: ignore[attr-defined]  # aiosmtpd hook
    with raises_exactly(
        DeliveryError,
        "the server refused the sender rechnung@muster.example",
    ) as error:
        SmtpSender().send(settings(plain, MailSecurity.NONE, username="", password=""), MAIL)
    assert error.value.code == "mail_sender_refused"
    assert error.value.details == {"server": "553 5.7.1 sender not allowed"}


def test_a_mail_too_large(inbox: Inbox) -> None:
    controller = Controller(inbox, hostname=HOST, port=free_port(), data_size_limit=100)
    controller.start()
    try:
        server = MailServer(
            host=HOST, port=int(controller.port), security=MailSecurity.NONE, sender=SENDER
        )
        with raises_exactly(DeliveryError, "the mail is larger than the server takes") as error:
            SmtpSender().send(server, MAIL)
    finally:
        controller.stop()
    assert error.value.code == "mail_too_large"


def test_international_addresses_need_smtputf8(inbox: Inbox) -> None:
    controller = Controller(inbox, hostname=HOST, port=free_port(), enable_SMTPUTF8=False)
    controller.start()
    try:
        server = MailServer(
            host=HOST, port=int(controller.port), security=MailSecurity.NONE, sender=SENDER
        )
        with raises_exactly(
            DeliveryError, "the server takes no addresses with accents or umlauts"
        ) as error:
            SmtpSender().send(
                server,
                OutgoingMail(to=(EmailAddress("info@müller.example"),), subject="x", body="y"),
            )
    finally:
        controller.stop()
    assert error.value.code == "mail_utf8_unsupported"


def test_the_message_names_no_blind_copies() -> None:
    server = MailServer(host="smtp.example", port=25, security=MailSecurity.NONE, sender=SENDER)
    built = message(server, MAIL)
    assert built["Bcc"] is None
    assert built["To"] == "buchhaltung@kunde.example"
