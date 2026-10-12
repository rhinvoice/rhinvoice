"""The mail server and the company's mail templates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from rhinvoice.domain.mail.server import MailSecurity, MailServer
from rhinvoice.domain.mail.template import MailKind, MailTemplate
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.language import Language
from rhinvoice.infrastructure.db.tables import mail_server, mail_templates

if TYPE_CHECKING:
    from sqlalchemy import Connection


class SqlMailRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def server(self) -> MailServer | None:
        row = self._connection.execute(select(mail_server)).mappings().first()
        if row is None:
            return None
        return MailServer(
            host=row["host"],
            port=row["port"],
            security=MailSecurity(row["security"]),
            sender=EmailAddress(row["sender"]),
            sender_name=row["sender_name"],
            username=row["username"],
            password=row["password"],
            reply_to=None if row["reply_to"] is None else EmailAddress(row["reply_to"]),
            copy_to_sender=row["copy_to_sender"],
        )

    def save_server(self, server: MailServer) -> None:
        values = {
            "host": server.host,
            "port": server.port,
            "security": server.security.value,
            "sender": str(server.sender),
            "sender_name": server.sender_name,
            "username": server.username,
            "password": server.password,
            "reply_to": None if server.reply_to is None else str(server.reply_to),
            "copy_to_sender": server.copy_to_sender,
        }
        statement = pg_insert(mail_server).values(singleton=True, **values)
        self._connection.execute(
            statement.on_conflict_do_update(index_elements=[mail_server.c.singleton], set_=values)
        )

    def templates(self) -> dict[tuple[MailKind, Language], MailTemplate]:
        rows = self._connection.execute(select(mail_templates)).mappings()
        found: dict[tuple[MailKind, Language], MailTemplate] = {}
        for row in rows:
            template = MailTemplate(
                MailKind(row["kind"]), Language(row["language"]), row["subject"], row["body"]
            )
            found[template.kind, template.language] = template
        return found

    def save_template(self, template: MailTemplate) -> None:
        statement = pg_insert(mail_templates).values(
            kind=template.kind.value,
            language=template.language.value,
            subject=template.subject,
            body=template.body,
        )
        self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=[mail_templates.c.kind, mail_templates.c.language],
                set_={"subject": statement.excluded.subject, "body": statement.excluded.body},
            )
        )

    def delete_template(self, kind: MailKind, language: Language) -> None:
        self._connection.execute(
            delete(mail_templates).where(
                mail_templates.c.kind == kind.value, mail_templates.c.language == language.value
            )
        )
