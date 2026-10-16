"""The mail server, the mail templates and recipients."""

import pytest

from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.mail.message import MAX_RECIPIENTS, recipients
from rhinvoice.domain.mail.server import MailSecurity, MailServer
from rhinvoice.domain.mail.template import MailKind, MailTemplate, default_template
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.text.template import unknown_placeholders
from tests.helpers import raises_exactly

SENDER = EmailAddress("rechnung@muster.example")


def server(**overrides: object) -> MailServer:
    values: dict[str, object] = {
        "host": "smtp.muster.example",
        "port": 587,
        "security": MailSecurity.STARTTLS,
        "sender": SENDER,
    }
    values.update(overrides)
    return MailServer(**values)  # type: ignore[arg-type]  # test builder


def test_a_server_is_cleaned() -> None:
    cleaned = server(host=" smtp.muster.example ", sender_name=" Muster GmbH ", username=" u ")
    assert (cleaned.host, cleaned.sender_name, cleaned.username) == (
        "smtp.muster.example",
        "Muster GmbH",
        "u",
    )
    assert cleaned.copy_to_sender
    assert cleaned.reply_to is None
    # Spaces are part of a password.
    assert server(username="u", password=" geheim ").password == " geheim "


@pytest.mark.parametrize(
    ("overrides", "field", "message"),
    [
        ({"host": " "}, "host", "host is required"),
        (
            {"host": "smtp://muster.example"},
            "host",
            "the server is a host name or IP address, e.g. smtp.example.com",
        ),
        (
            {"host": "user@muster.example"},
            "host",
            "the server is a host name or IP address, e.g. smtp.example.com",
        ),
        (
            {"host": "smtp muster"},
            "host",
            "the server is a host name or IP address, e.g. smtp.example.com",
        ),
        ({"host": "a" * 254}, "host", "host must be at most 253 characters long"),
        ({"port": 0}, "port", "the port must be between 1 and 65535"),
        ({"port": 65_536}, "port", "the port must be between 1 and 65535"),
        ({"password": "x"}, "username", "a password needs a user name"),
        (
            {"host": "smtp.example.com:587"},
            "host",
            "the server is a host name or IP address, e.g. smtp.example.com",
        ),
        (
            {"host": "smtp/x"},
            "host",
            "the server is a host name or IP address, e.g. smtp.example.com",
        ),
        (
            {"username": "u", "security": MailSecurity.NONE},
            "security",
            "a login needs an encrypted connection",
        ),
        (
            {"username": "u", "password": "a\nb"},
            "password",
            "the password is too long or contains control characters",
        ),
        (
            {"username": "u", "password": "x" * 501},
            "password",
            "the password is too long or contains control characters",
        ),
        (
            {"sender_name": "x" * 121},
            "sender_name",
            "sender_name must be at most 120 characters long",
        ),
        ({"username": "u" * 255}, "username", "username must be at most 254 characters long"),
    ],
)
def test_server_rules(overrides: dict[str, object], field: str, message: str) -> None:
    with raises_exactly(ValidationError, message) as error:
        server(**overrides)
    assert error.value.field == field
    if field == "security":
        assert error.value.code == "mail_login_needs_tls"


def test_the_password_is_never_printed() -> None:
    shown = repr(server(username="u", password="geheim"))
    assert "geheim" not in shown
    assert "smtp.muster.example" in shown
    # A relay in the own network needs neither login nor encryption.
    assert server(security=MailSecurity.NONE, port=25).username == ""


def test_limits_are_inclusive() -> None:
    assert server(port=1).port == 1
    assert server(port=65_535).port == 65_535
    assert len(server(host="a" * 253).host) == 253
    # Capital letters and IP addresses are host names too.
    assert server(host="MX.Example.com").host == "MX.Example.com"
    assert server(host="192.168.1.10").host == "192.168.1.10"
    assert len(server(username="u", password="x" * 500).password) == 500
    assert len(server(sender_name="x" * 120).sender_name) == 120


def test_default_ports() -> None:
    assert [security.default_port for security in MailSecurity] == [587, 465, 25]


def test_kinds() -> None:
    assert MailKind.of_document(DocumentType.INVOICE) is MailKind.INVOICE
    assert MailKind.of_document(DocumentType.QUOTE) is MailKind.QUOTE
    assert MailKind.of_document(DocumentType.CANCELLATION) is MailKind.CANCELLATION
    assert [MailKind.of_reminder(level) for level in (1, 2, 3)] == [
        MailKind.REMINDER_1,
        MailKind.REMINDER_2,
        MailKind.REMINDER_3,
    ]


def test_default_templates_greet_like_the_country() -> None:
    swiss = default_template(MailKind.INVOICE, Language.DE, Country.LI)
    assert swiss.subject == "Rechnung {nummer}"
    assert swiss.body == (
        "Guten Tag\n\nIm Anhang erhalten Sie unsere Rechnung {nummer} über {waehrung} {betrag},"
        " zahlbar bis {faellig}.\n\nFreundliche Grüsse\n{firma}"
    )
    german = default_template(MailKind.REMINDER_2, Language.DE, Country.AT)
    assert german.subject == "1. Mahnung zur Rechnung {nummer}"
    assert german.body.startswith("Guten Tag\n\nTrotz unserer Zahlungserinnerung")
    assert german.body.endswith("\n\nMit freundlichen Grüßen\n{firma}")
    english = default_template(MailKind.QUOTE, Language.EN, Country.CH)
    assert english.subject == "Quote {nummer}"
    assert english.body.startswith("Dear Sir or Madam\n\nPlease find attached our quote")
    assert english.body.endswith("\n\nKind regards\n{firma}")
    french = default_template(MailKind.CANCELLATION, Language.FR, Country.CH)
    assert french.subject == "Note de crédit {nummer}"
    assert french.body == (
        "Bonjour\n\nVeuillez trouver ci-joint la note de crédit {nummer}."
        "\n\nMeilleures salutations\n{firma}"
    )
    italian = default_template(MailKind.REMINDER_1, Language.IT, Country.CH)
    assert italian.subject == "Promemoria di pagamento per la fattura {nummer}"
    assert italian.body.startswith("Buongiorno\n\nLa nostra fattura {nummer}")
    assert italian.body.endswith("\n\nCordiali saluti\n{firma}")


def test_every_default_template_is_valid() -> None:
    for kind in MailKind:
        for language in Language:
            for country in Country:
                template = default_template(kind, language, country)
                assert unknown_placeholders(template.subject + template.body) == []
                assert "{nummer}" in template.subject
    # Each language words its mails itself.
    bodies = {
        default_template(MailKind.INVOICE, language, Country.CH).body for language in Language
    }
    assert len(bodies) == len(Language)


def test_template_rules() -> None:
    template = MailTemplate(MailKind.INVOICE, Language.DE, " Rechnung {nummer} ", " Hallo\r\n ")
    assert (template.subject, template.body) == ("Rechnung {nummer}", "Hallo")
    with raises_exactly(ValidationError, "subject is required") as subject:
        MailTemplate(MailKind.INVOICE, Language.DE, " ", "x")
    assert subject.value.field == "subject"
    with raises_exactly(
        ValidationError, "subject must not contain line breaks or control characters"
    ):
        MailTemplate(MailKind.INVOICE, Language.DE, "a\nb", "x")
    with raises_exactly(ValidationError, "body is required") as body:
        MailTemplate(MailKind.INVOICE, Language.DE, "x", " \n ")
    assert body.value.field == "body"
    with raises_exactly(ValidationError, "body must be at most 5000 characters long"):
        MailTemplate(MailKind.INVOICE, Language.DE, "x", "y" * 5001)
    assert len(MailTemplate(MailKind.INVOICE, Language.DE, "x" * 200, "y" * 5000).body) == 5000
    with raises_exactly(ValidationError, "subject must be at most 200 characters long"):
        MailTemplate(MailKind.INVOICE, Language.DE, "x" * 201, "y")
    for field, subject_text, body_text in (
        ("subject", "Rechnung {nr}", "x"),
        ("body", "x", "Hallo {name} {nummer}"),
    ):
        with raises_exactly(
            ValidationError,
            f"unknown placeholder {{{'nr' if field == 'subject' else 'name'}}}; available are"
            " {nummer}, {datum}, {faellig}, {kunde}, {betrag}, {waehrung}, {firma}",
        ) as unknown:
            MailTemplate(MailKind.INVOICE, Language.DE, subject_text, body_text)
        assert (unknown.value.field, unknown.value.code) == (field, "unknown_placeholder")


def test_recipients() -> None:
    assert recipients([" Anna@Example.com ", "", "anna@example.com", "b@example.com"]) == (
        EmailAddress("anna@example.com"),
        EmailAddress("b@example.com"),
    )
    with raises_exactly(ValidationError, "the mail needs a recipient") as missing:
        recipients([" "])
    assert (missing.value.field, missing.value.code) == ("to", "recipient_missing")
    with raises_exactly(ValidationError, "'anna' is not a valid e-mail address") as invalid:
        recipients(["anna"])
    assert (invalid.value.field, invalid.value.code) == ("to", "invalid_recipient")
    # The header and the server must read an address alike.
    for tricky in ("a,b@example.com", "x<ceo@corp.example>", 'a"b@example.com', "müller@x.example"):
        with raises_exactly(ValidationError, f"'{tricky}' is not a plain e-mail address") as plain:
            recipients([tricky])
        assert (plain.value.field, plain.value.code) == ("to", "invalid_recipient")
    many = [f"p{index}@example.com" for index in range(MAX_RECIPIENTS)]
    assert len(recipients(many)) == MAX_RECIPIENTS
    with raises_exactly(ValidationError, "a mail goes to at most 5 recipients") as too_many:
        recipients([*many, "late@example.com"])
    assert too_many.value.field == "to"
