"""Sending documents and reminders by mail, with a fake server and fake files."""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import timedelta
from uuid import UUID

import pytest

from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.dunning.handlers import DunningHandlers
from rhinvoice.application.errors import DeliveryError, NotFoundError, UnavailableError
from rhinvoice.application.mail.handlers import MailHandlers, SaveMailServer, SendMail
from rhinvoice.application.mail.ports import Attachment, MailValues, OutgoingMail
from rhinvoice.domain.document.document import DocumentType, EventKind
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.dunning.reminder import Reminder
from rhinvoice.domain.mail.server import MailSecurity, MailServer
from rhinvoice.domain.mail.template import MailKind, MailTemplate, default_template
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import Country, CountryCode
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.text.template import Placeholder
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)
TODAY = NOW.date()
LINE = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="100")
SENDER = EmailAddress("rechnung@muster.example")
CUSTOMER_MAIL = EmailAddress("buchhaltung@kunde.example")
PDF = Attachment("Rechnung.pdf", b"%PDF", "application/pdf")
XML = Attachment("XRechnung.xml", b"<x/>", "application/xml")
LETTER = Attachment("Zahlungserinnerung.pdf", b"%PDF-r", "application/pdf")


@dataclass
class FakeSender:
    sent: list[tuple[MailServer, OutgoingMail]] = field(
        default_factory=list[tuple[MailServer, OutgoingMail]]
    )
    error: DeliveryError | None = None
    meanwhile: Callable[[], None] | None = None
    """Something that happens while the mail is on its way."""
    refuse: tuple[str, ...] = ()
    """Recipients the server refuses while it takes the others."""

    def send(self, server: MailServer, mail: OutgoingMail) -> tuple[str, ...]:
        if self.error is not None:
            raise self.error
        self.sent.append((server, mail))
        if self.meanwhile is not None:
            self.meanwhile()
        everyone = {str(address) for address in (*mail.to, *mail.bcc)}
        return tuple(address for address in self.refuse if address in everyone)


@dataclass
class FakeContent:
    asked: list[tuple[UUID, bool]] = field(default_factory=list[tuple[UUID, bool]])

    def document_values(self, view: object) -> MailValues:
        number = getattr(getattr(view, "document"), "number")  # noqa: B009 - duck-typed fake
        return MailValues(
            {Placeholder.NUMBER: number, Placeholder.COMPANY: "Muster GmbH"}, "Rechnung.pdf"
        )

    def document_files(self, document_id: UUID, *, xrechnung: bool) -> tuple[Attachment, ...]:
        self.asked.append((document_id, xrechnung))
        return (PDF, XML) if xrechnung else (PDF,)

    def reminder_values(self, reminder: Reminder) -> MailValues:
        return MailValues({Placeholder.NUMBER: f"Stufe {reminder.level}"}, "Erinnerung.pdf")

    def reminder_files(self, reminder: Reminder) -> tuple[Attachment, ...]:
        self.asked.append((reminder.id, False))
        return (LETTER,)


@pytest.fixture
def documents(store: Store, clock: FixedClock) -> DocumentHandlers:
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER, email=CUSTOMER_MAIL)
    return DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture
def content() -> FakeContent:
    return FakeContent()


@pytest.fixture
def mail(
    store: Store,
    clock: FixedClock,
    documents: DocumentHandlers,
    sender: FakeSender,
    content: FakeContent,
) -> MailHandlers:
    return MailHandlers(
        uow=lambda: InMemoryUnitOfWork(store),
        clock=clock,
        documents=documents,
        content=content,
        sender=sender,
    )


def configure(mail: MailHandlers, **overrides: object) -> None:
    values: dict[str, object] = {
        "host": "smtp.muster.example",
        "port": 587,
        "security": MailSecurity.STARTTLS,
        "sender": "Rechnung@Muster.example",
        "username": "rechnung",
        "password": "geheim",
    }
    values.update(overrides)
    mail.save_server(SaveMailServer(**values))  # type: ignore[arg-type]  # test builder


def issued(documents: DocumentHandlers, document_type: DocumentType = DocumentType.INVOICE) -> UUID:
    created = documents.create(document_type, DraftInput(customer_id=CUSTOMER, lines=(LINE,)))
    return documents.issue(created.document.id).document.id


def test_the_server_is_saved_without_showing_its_password(mail: MailHandlers, store: Store) -> None:
    assert mail.server().server is None
    assert mail.server().password_set is False
    # A first server with a user but no password has none.
    configure(mail, password=None)
    assert mail.server().password_set is False
    configure(mail, sender_name="Muster GmbH", reply_to=" Info@Muster.example ")
    view = mail.server()
    assert view.password_set
    assert view.server is not None
    assert (
        view.server.password,
        view.server.sender,
        view.server.sender_name,
        view.server.reply_to,
    ) == ("", SENDER, "Muster GmbH", EmailAddress("info@muster.example"))
    assert store.mail_server is not None
    assert store.mail_server.password == "geheim"
    # No password in the form keeps the stored one, for the same server, port and user.
    configure(mail, password=None, host=" smtp.muster.example ", security=MailSecurity.TLS)
    assert (store.mail_server.password, store.mail_server.security) == ("geheim", MailSecurity.TLS)
    # Another server, port or user must not get the stored password at the next login.
    for changed in ({"host": "smtp.other.example"}, {"port": 465}, {"username": "other"}):
        with raises_exactly(
            ValidationError, "enter the password again for the changed server or user"
        ) as again:
            configure(mail, password=None, **changed)
        assert (again.value.field, again.value.code) == ("password", "mail_password_required")
    assert store.mail_server.host == "smtp.muster.example"
    configure(mail, password="neu", port=465)
    assert (store.mail_server.password, store.mail_server.port) == ("neu", 465)
    # An empty password removes it.
    configure(mail, password="")
    assert store.mail_server.password == ""
    assert not mail.server().password_set
    # Without a user name there is no login and nothing to keep.
    configure(mail, password="geheim")
    configure(mail, username=" ", password=None)
    assert store.mail_server.password == ""
    configure(mail, password="geheim")
    configure(mail, username=" ", password="x")
    assert (store.mail_server.username, store.mail_server.password) == ("", "")
    assert store.mail_server.reply_to is None


def test_a_first_server_without_password(mail: MailHandlers, store: Store) -> None:
    configure(mail, username="", password=None, security=MailSecurity.NONE, port=25)
    assert store.mail_server is not None
    assert store.mail_server.password == ""


def test_server_addresses_are_checked(mail: MailHandlers) -> None:
    with raises_exactly(ValidationError, "'rechnung' is not a valid e-mail address") as sender:
        configure(mail, sender="rechnung")
    assert sender.value.field == "sender"
    with raises_exactly(ValidationError, "'info' is not a valid e-mail address") as reply:
        configure(mail, reply_to="info")
    assert reply.value.field == "reply_to"


def test_a_test_mail_goes_out_in_the_company_language(
    mail: MailHandlers, sender: FakeSender, store: Store
) -> None:
    with raises_exactly(
        UnavailableError, "set up the mail server first (Settings → E-mail)"
    ) as missing:
        mail.send_test("anna@example.com")
    assert missing.value.code == "mail_not_configured"
    configure(mail)
    mail.send_test(" Anna@Example.com ")
    [(server, sent)] = sender.sent
    assert server.password == "geheim"
    assert sent == OutgoingMail(
        to=(EmailAddress("anna@example.com"),),
        subject="Rhinvoice: Test-E-Mail",
        body=("Diese E-Mail bestätigt, dass Rhinvoice über den eingerichteten Server senden kann."),
    )
    assert store.company is not None
    store.company = replace(store.company, default_language=Language.EN)
    mail.send_test("anna@example.com")
    assert sender.sent[-1][1].subject == "Rhinvoice: test mail"


def test_templates_are_built_in_until_changed(mail: MailHandlers, store: Store) -> None:
    views = mail.templates()
    assert len(views) == len(MailKind) * len(Language)
    first = views[0]
    assert (first.template.kind, first.template.language, first.customized) == (
        MailKind.INVOICE,
        Language.DE,
        False,
    )
    assert (
        first.template
        == first.default
        == default_template(MailKind.INVOICE, Language.DE, Country.CH)
    )
    saved = mail.save_template(MailKind.QUOTE, Language.EN, " Our quote {nummer} ", "Hello")
    assert saved.customized
    assert saved.template == MailTemplate(
        MailKind.QUOTE, Language.EN, "Our quote {nummer}", "Hello"
    )
    assert store.mail_templates == {(MailKind.QUOTE, Language.EN): saved.template}
    listed = next(
        view
        for view in mail.templates()
        if (view.template.kind, view.template.language) == (MailKind.QUOTE, Language.EN)
    )
    assert listed == saved
    # The built-in wording, or nothing at all, restores the default.
    default = saved.default
    for subject, body in ((default.subject, default.body), (" ", " ")):
        mail.save_template(MailKind.QUOTE, Language.EN, "x", "y")
        restored = mail.save_template(MailKind.QUOTE, Language.EN, subject, body)
        assert (restored.template, restored.customized) == (default, False)
        assert store.mail_templates == {}
    with raises_exactly(ValidationError, "body is required"):
        mail.save_template(MailKind.QUOTE, Language.EN, "Subject only", " ")
    # The built-in wording follows the company's country.
    assert store.company is not None
    store.company = replace(store.company, address=factories.address(country=CountryCode("DE")))
    german = mail.save_template(MailKind.INVOICE, Language.DE, "", "")
    assert german.template.body.endswith("Mit freundlichen Grüßen\n{firma}")


def test_a_document_mail_is_prepared_for_its_customer(
    mail: MailHandlers, documents: DocumentHandlers, store: Store
) -> None:
    invoice = issued(documents)
    draft = mail.document_draft(invoice)
    number = documents.get(invoice).document.number
    assert draft.to == ("buchhaltung@kunde.example",)
    assert draft.subject == f"Rechnung {number}"
    assert draft.body.startswith("Guten Tag\n\nIm Anhang erhalten Sie unsere Rechnung")
    assert draft.body.endswith("Freundliche Grüsse\nMuster GmbH")
    assert draft.attachment == "Rechnung.pdf"
    assert draft.copy_to is None
    configure(mail)
    assert mail.document_draft(invoice).copy_to == "rechnung@muster.example"
    configure(mail, copy_to_sender=False)
    assert mail.document_draft(invoice).copy_to is None
    # The company's own template, and customers without an address.
    mail.save_template(MailKind.INVOICE, Language.DE, "R {nummer}", "Hallo {kunde}")
    store.customers[CUSTOMER] = replace(store.customers[CUSTOMER], email=None)
    own = mail.document_draft(invoice)
    assert (own.to, own.subject, own.body) == ((), f"R {number}", "Hallo {kunde}")
    # A customer removed meanwhile: nobody to prefill.
    del store.customers[CUSTOMER]
    assert mail.document_draft(invoice).to == ()


def test_quotes_and_cancellations_have_their_own_mail(
    mail: MailHandlers, documents: DocumentHandlers
) -> None:
    quote = issued(documents, DocumentType.QUOTE)
    assert mail.document_draft(quote).subject.startswith("Angebot ")
    cancellation = documents.cancel(issued(documents)).document.cancelled_by_id
    assert cancellation is not None
    assert mail.document_draft(cancellation).subject.startswith("Stornorechnung ")


def test_drafts_are_not_mailed(mail: MailHandlers, documents: DocumentHandlers) -> None:
    draft = documents.create(
        DocumentType.INVOICE, DraftInput(customer_id=CUSTOMER, lines=(LINE,))
    ).document.id
    with raises_exactly(ValidationError, "drafts are not sent; issue the document first") as error:
        mail.document_draft(draft)
    assert (error.value.field, error.value.code) == ("document", "mail_draft")
    configure(mail)
    with raises_exactly(ValidationError, "drafts are not sent; issue the document first"):
        mail.send_document(draft, SendMail(to=("a@example.com",), subject="x", body="y"))


def test_sending_a_document_attaches_it_and_notes_it(
    mail: MailHandlers,
    documents: DocumentHandlers,
    sender: FakeSender,
    content: FakeContent,
    clock: FixedClock,
) -> None:
    invoice = issued(documents)
    command = SendMail(
        to=("buchhaltung@kunde.example", "Chef@Kunde.example"),
        subject=" Rechnung ",
        body=" Guten Tag\r\n ",
        xrechnung=True,
    )
    with raises_exactly(UnavailableError, "set up the mail server first (Settings → E-mail)"):
        mail.send_document(invoice, command)
    assert content.asked == []
    configure(mail)
    clock.set(NOW + timedelta(minutes=5))
    view = mail.send_document(invoice, command)
    [(server, sent)] = sender.sent
    assert (server.host, server.password) == ("smtp.muster.example", "geheim")
    assert sent == OutgoingMail(
        to=(CUSTOMER_MAIL, EmailAddress("chef@kunde.example")),
        subject="Rechnung",
        body="Guten Tag",
        attachments=(PDF, XML),
        bcc=(SENDER,),
    )
    assert content.asked == [(invoice, True)]
    event = view.document.events[-1]
    assert (event.kind, event.detail, event.at) == (
        EventKind.EMAILED,
        "buchhaltung@kunde.example, chef@kunde.example",
        NOW + timedelta(minutes=5),
    )
    assert documents.get(invoice).document.events[-1] == event


def test_the_sender_gets_no_copy_of_a_mail_to_itself(
    mail: MailHandlers, documents: DocumentHandlers, sender: FakeSender
) -> None:
    configure(mail)
    invoice = issued(documents)
    mail.send_document(invoice, SendMail(to=(str(SENDER),), subject="R", body="x"))
    configure(mail, copy_to_sender=False)
    mail.send_document(invoice, SendMail(to=("a@example.com",), subject="R", body="x"))
    assert [sent.bcc for _, sent in sender.sent] == [(), ()]


def test_what_is_checked_before_sending(
    mail: MailHandlers, documents: DocumentHandlers, sender: FakeSender
) -> None:
    configure(mail)
    invoice = issued(documents)
    quote = issued(documents, DocumentType.QUOTE)
    for document_id, command, message, field_name in (
        (invoice, SendMail(to=(), subject="R", body="x"), "the mail needs a recipient", "to"),
        (
            invoice,
            SendMail(to=("a@example.com",), subject=" ", body="x"),
            "subject is required",
            "subject",
        ),
        (
            invoice,
            SendMail(to=("a@example.com",), subject="R", body=" "),
            "body is required",
            "body",
        ),
        (
            invoice,
            SendMail(to=("a@example.com",), subject="R", body="a\x00b"),
            "body must not contain control characters",
            "body",
        ),
        (
            quote,
            SendMail(to=("a@example.com",), subject="R", body="x", xrechnung=True),
            "quotes are no e-invoices",
            "xrechnung",
        ),
    ):
        with raises_exactly(ValidationError, message) as error:
            mail.send_document(document_id, command)
        assert error.value.field == field_name
    assert sender.sent == []
    # A quote goes out without XRechnung.
    mail.send_document(quote, SendMail(to=("a@example.com",), subject="A", body="x"))
    assert len(sender.sent) == 1


def test_refused_recipients(
    mail: MailHandlers, documents: DocumentHandlers, sender: FakeSender
) -> None:
    configure(mail)
    invoice = issued(documents)
    command = SendMail(to=("a@example.com", "b@example.com"), subject="R", body="x")
    # Only the copy to the sender refused: the customer has it, nothing to report.
    sender.refuse = (str(SENDER),)
    noted = mail.send_document(invoice, command)
    assert noted.document.events[-1].detail == "a@example.com, b@example.com"
    # One of two refused: the other got it, the history says so, the person learns who did not.
    sender.refuse = ("b@example.com",)
    with raises_exactly(
        DeliveryError,
        "the server refused b@example.com; the other recipients received the mail",
    ) as partly:
        mail.send_document(invoice, command)
    assert (partly.value.code, partly.value.details) == (
        "mail_partly_refused",
        {"refused": "b@example.com"},
    )
    assert documents.get(invoice).document.events[-1].detail == "a@example.com"
    # Every recipient refused: nothing went out, nothing is noted.
    events = documents.get(invoice).document.events
    sender.refuse = ("a@example.com", "b@example.com")
    with raises_exactly(
        DeliveryError, "the server refused the recipient a@example.com, b@example.com"
    ) as refused:
        mail.send_document(invoice, command)
    assert refused.value.code == "mail_recipient_refused"
    assert documents.get(invoice).document.events == events


def test_long_recipient_lists_fit_the_history(
    mail: MailHandlers, documents: DocumentHandlers
) -> None:
    configure(mail)
    invoice = issued(documents)
    long = [f"{'x' * 200}{index}@example.com" for index in range(5)]
    view = mail.send_document(invoice, SendMail(to=tuple(long), subject="R", body="x"))
    detail = view.document.events[-1].detail
    assert detail == f"{long[0]}, {long[1]} (+3)"
    assert len(detail) <= 500
    # Exactly 500 characters still fit, one more does not.
    two = [f"{'a' * 233}@example.com", f"{'b' * 241}@example.com"]
    assert len(", ".join(two)) == 500
    fits = mail.send_document(invoice, SendMail(to=tuple(two), subject="R", body="x"))
    assert fits.document.events[-1].detail == ", ".join(two)
    longer = [two[0], f"{'b' * 242}@example.com"]
    cut = mail.send_document(invoice, SendMail(to=tuple(longer), subject="R", body="x"))
    assert cut.document.events[-1].detail == f"{two[0]} (+1)"


def test_a_refused_mail_is_not_noted(
    mail: MailHandlers, documents: DocumentHandlers, sender: FakeSender
) -> None:
    configure(mail)
    invoice = issued(documents)
    events = documents.get(invoice).document.events
    sender.error = DeliveryError("the server refused the login", code="mail_auth_failed")
    with raises_exactly(DeliveryError, "the server refused the login") as error:
        mail.send_document(invoice, SendMail(to=("a@example.com",), subject="R", body="x"))
    assert error.value.code == "mail_auth_failed"
    assert documents.get(invoice).document.events == events


def test_reminders_are_mailed_with_their_letter(
    mail: MailHandlers,
    *,
    documents: DocumentHandlers,
    store: Store,
    clock: FixedClock,
    sender: FakeSender,
    content: FakeContent,
) -> None:
    invoice = issued(documents)
    clock.set(NOW + timedelta(days=45))
    dunning = DunningHandlers(
        uow=lambda: InMemoryUnitOfWork(store), clock=clock, documents=documents
    )
    reminder, _ = dunning.remind(invoice, level=1)
    draft = mail.reminder_draft(reminder.id)
    assert draft.subject == "Zahlungserinnerung zur Rechnung Stufe 1"
    assert draft.attachment == "Erinnerung.pdf"
    assert draft.to == ("buchhaltung@kunde.example",)
    configure(mail)
    view = mail.send_reminder(
        reminder.id,
        SendMail(to=("buchhaltung@kunde.example",), subject="Erinnerung", body="x", xrechnung=True),
    )
    [(_, sent)] = sender.sent
    assert sent.attachments == (LETTER,)
    assert content.asked == [(reminder.id, False)]
    # Some recipients refused: the others are noted, the refused ones named.
    sender.refuse = ("b@example.com",)
    with raises_exactly(
        DeliveryError,
        "the server refused b@example.com; the other recipients received the mail",
    ):
        mail.send_reminder(
            reminder.id, SendMail(to=("a@example.com", "b@example.com"), subject="R", body="x")
        )
    assert documents.get(invoice).document.events[-1].detail == "1 a@example.com"
    sender.refuse = ()
    assert (view.document.id, view.document.events[-1].kind, view.document.events[-1].detail) == (
        invoice,
        EventKind.REMINDER_EMAILED,
        "1 buchhaltung@kunde.example",
    )
    # Paid meanwhile: its reminders are not sent any more.
    documents.mark_paid(invoice, TODAY)
    for call in (
        lambda: mail.reminder_draft(reminder.id),
        lambda: mail.send_reminder(
            reminder.id, SendMail(to=("a@example.com",), subject="R", body="x")
        ),
    ):
        with raises_exactly(
            InvalidStateError, "the invoice is no longer open; its reminders are not sent"
        ) as closed:
            call()
        assert closed.value.code == "reminder_not_open"
    with raises_exactly(NotFoundError, "reminder not found"):
        mail.reminder_draft(new_id())
    with raises_exactly(NotFoundError, "reminder not found"):
        mail.send_reminder(new_id(), SendMail(to=("a@example.com",), subject="R", body="x"))


def test_mails_need_the_company(mail: MailHandlers, store: Store) -> None:
    store.company = None
    with raises_exactly(ValidationError, "please set up the company first") as error:
        mail.templates()
    assert error.value.field == "company"


def test_the_document_is_locked_while_its_mail_is_noted(
    store: Store, documents: DocumentHandlers, content: FakeContent, sender: FakeSender
) -> None:
    units: list[InMemoryUnitOfWork] = []

    def uow() -> InMemoryUnitOfWork:
        unit = InMemoryUnitOfWork(store)
        units.append(unit)
        return unit

    watched = MailHandlers(
        uow=uow, clock=documents.clock, documents=documents, content=content, sender=sender
    )
    configure(watched)
    invoice = issued(documents)
    units.clear()
    watched.send_document(invoice, SendMail(to=("a@example.com",), subject="R", body="x"))
    assert [locked for unit in units for locked in unit.documents.locked] == [invoice]


def test_a_document_that_vanished_while_sending(
    mail: MailHandlers, documents: DocumentHandlers, store: Store, sender: FakeSender
) -> None:
    configure(mail)
    invoice = issued(documents)

    def vanish() -> None:
        del store.documents[invoice]

    sender.meanwhile = vanish
    with raises_exactly(NotFoundError, "document not found"):
        mail.send_document(invoice, SendMail(to=("a@example.com",), subject="R", body="x"))
