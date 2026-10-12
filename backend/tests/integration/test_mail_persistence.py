"""The mail server and the mail templates in PostgreSQL."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from rhinvoice.domain.mail.server import MailSecurity, MailServer
from rhinvoice.domain.mail.template import MailKind, MailTemplate
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.language import Language
from rhinvoice.infrastructure.db.uow import SqlUnitOfWork

SERVER = MailServer(
    host="smtp.muster.example",
    port=587,
    security=MailSecurity.STARTTLS,
    sender=EmailAddress("rechnung@muster.example"),
    sender_name="Muster GmbH",
    username="rechnung",
    password=" geheim ",
    reply_to=EmailAddress("info@muster.example"),
    copy_to_sender=False,
)


def test_the_server_is_saved_and_replaced(engine: Engine) -> None:
    with SqlUnitOfWork(engine) as uow:
        assert uow.mail.server() is None
        uow.mail.save_server(SERVER)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.mail.server() == SERVER
        relay = MailServer(
            host="relay.local",
            port=25,
            security=MailSecurity.NONE,
            sender=EmailAddress("noreply@muster.example"),
        )
        uow.mail.save_server(relay)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.mail.server() == relay
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO mail_server (singleton, host, port, security, sender, copy_to_sender)"
                " VALUES (false, 'x', 25, 'none', 'a@b.c', true)"
            )
        )


def test_templates_are_saved_per_kind_and_language(engine: Engine) -> None:
    own = MailTemplate(MailKind.REMINDER_2, Language.EN, "Reminder {nummer}", "Hello\n\nPay.")
    other = MailTemplate(MailKind.REMINDER_2, Language.DE, "Mahnung {nummer}", "Hallo")
    with SqlUnitOfWork(engine) as uow:
        assert uow.mail.templates() == {}
        uow.mail.save_template(own)
        uow.mail.save_template(other)
        uow.mail.save_template(own)
        uow.commit()
    changed = MailTemplate(MailKind.REMINDER_2, Language.EN, "Second {nummer}", "Pay now.")
    with SqlUnitOfWork(engine) as uow:
        assert uow.mail.templates() == {
            (MailKind.REMINDER_2, Language.EN): own,
            (MailKind.REMINDER_2, Language.DE): other,
        }
        uow.mail.save_template(changed)
        uow.mail.delete_template(MailKind.REMINDER_2, Language.DE)
        uow.commit()
    with SqlUnitOfWork(engine) as uow:
        assert uow.mail.templates() == {(MailKind.REMINDER_2, Language.EN): changed}
