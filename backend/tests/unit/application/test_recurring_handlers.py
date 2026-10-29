"""Recurring invoice plans and the run that writes their invoices."""

import logging
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

import pytest

from rhinvoice.application.document.handlers import (
    DocumentHandlers,
    DocumentView,
    DraftInput,
    LineInput,
)
from rhinvoice.application.document.printing import PrintHandlers
from rhinvoice.application.errors import DeliveryError, NotFoundError
from rhinvoice.application.mail.handlers import MailHandlers, SaveMailServer
from rhinvoice.application.recurring.handlers import (
    RecurringHandlers,
    SavePlan,
    plan_draft,
    to_template,
)
from rhinvoice.domain.document.document import DocumentStatus, DocumentType, EventKind
from rhinvoice.domain.document.lines import DiscountKind, LineKind, PriceMode
from rhinvoice.domain.mail.server import MailSecurity
from rhinvoice.domain.recurring.plan import (
    Interval,
    PlanAction,
    PlanRun,
    RecurringPlan,
    RunOutcome,
)
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.email import EmailAddress
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.iban import Iban
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency, Money
from rhinvoice.domain.tax.category import TaxCategory
from rhinvoice.domain.tax.supply import Supply
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.application.test_mail_handlers import FakeContent, FakeSender
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)
TODAY = NOW.date()
HOSTING = LineInput(
    kind=LineKind.ITEM, description="Hosting", quantity="1", unit="MON", unit_price="29"
)
MAILBOX = EmailAddress("buchhaltung@kunde.example")


@pytest.fixture
def documents(store: Store, clock: FixedClock) -> DocumentHandlers:
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER, email=MAILBOX)
    return DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


@pytest.fixture
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture
def mail(
    store: Store, clock: FixedClock, documents: DocumentHandlers, sender: FakeSender
) -> MailHandlers:
    return MailHandlers(
        uow=lambda: InMemoryUnitOfWork(store),
        clock=clock,
        documents=documents,
        content=FakeContent(),
        sender=sender,
    )


@pytest.fixture
def recurring(
    store: Store, clock: FixedClock, documents: DocumentHandlers, mail: MailHandlers
) -> RecurringHandlers:
    def uow() -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(store)

    printing = PrintHandlers(
        uow=uow, clock=clock, documents=documents, renderer=JinjaDocumentRenderer()
    )
    return RecurringHandlers(
        uow=uow, clock=clock, documents=documents, printing=printing, mail=mail
    )


def save(**overrides: object) -> SavePlan:
    values: dict[str, object] = {
        "name": "Hosting",
        "customer_id": CUSTOMER,
        "interval": Interval.MONTHLY,
        "start_date": TODAY,
        "action": PlanAction.ISSUE,
        "template": DraftInput(
            customer_id=CUSTOMER,
            currency=Currency.CHF,
            lines=(HOSTING,),
            subject="Hosting",
            payment_text="Zahlbar bis {faellig}.",
        ),
    }
    values.update(overrides)
    return SavePlan(**values)  # type: ignore[arg-type]  # test builder


def at(clock: FixedClock, day: date) -> None:
    clock.set(datetime.combine(day, NOW.timetz()))


def test_plans_are_saved_with_their_template(recurring: RecurringHandlers, store: Store) -> None:
    created = recurring.create(save(end_date=date(2027, 12, 31)))
    plan = created.plan
    assert (plan.name, plan.next_date, plan.end_date, plan.active) == (
        "Hosting",
        TODAY,
        date(2027, 12, 31),
        True,
    )
    assert (created.customer_name, created.customer_archived) == ("Beispiel AG", False)
    store.customers[CUSTOMER] = store.customers[CUSTOMER].archive()
    assert recurring.get(created.plan.id).customer_archived
    store.customers[CUSTOMER] = store.customers[CUSTOMER].restore()
    # 29 + 8.1 % = 31.35, rounded to 31.35.
    assert created.total == Money(Decimal("31.35"), Currency.CHF)
    assert created.runs == ()
    assert store.plans[plan.id] == plan
    assert plan_draft(plan).lines[0].unit_price == "29"
    assert [view.plan for view in recurring.plans()] == [plan]
    assert recurring.get(plan.id).plan == plan


def test_templates_keep_what_the_editor_sent() -> None:
    template = to_template(
        DraftInput(
            customer_id=CUSTOMER,
            currency=Currency.EUR,
            language=Language.EN,
            price_mode=PriceMode.GROSS,
            lines=(
                LineInput(kind=LineKind.TEXT, description="Monthly"),
                replace(HOSTING, tax_category=TaxCategory.REDUCED, supply=Supply.GOODS),
            ),
            discount_kind=DiscountKind.AMOUNT,
            discount_value="5",
            reference="K-1",
            intro_text="Hello",
            closing_text="Thanks",
        )
    )
    assert template.discount is not None
    assert (template.discount.kind, template.discount.value) == (DiscountKind.AMOUNT, Decimal(5))
    assert (template.language, template.price_mode, template.reference) == (
        Language.EN,
        PriceMode.GROSS,
        "K-1",
    )
    assert [line.supply for line in template.lines] == [Supply.SERVICE, Supply.GOODS]
    plain = to_template(DraftInput(customer_id=CUSTOMER, currency=Currency.CHF, lines=(HOSTING,)))
    assert plain.discount is None
    with raises_exactly(ValidationError, "a plan names its currency"):
        to_template(DraftInput(customer_id=CUSTOMER, lines=(HOSTING,)))
    with raises_exactly(ValidationError, "the invoice needs at least one position with an amount"):
        to_template(DraftInput(customer_id=CUSTOMER, currency=Currency.CHF))


def test_plans_need_their_customer(recurring: RecurringHandlers) -> None:
    with raises_exactly(ValidationError, "the customer does not exist") as missing:
        recurring.create(save(customer_id=new_id()))
    assert missing.value.field == "customer_id"
    plan = recurring.create(save()).plan
    with raises_exactly(ValidationError, "the customer does not exist"):
        recurring.update(plan.id, save(customer_id=new_id()))
    for call in (recurring.get, recurring.pause, recurring.resume, recurring.delete):
        with raises_exactly(NotFoundError, "plan not found"):
            call(new_id())
    with raises_exactly(NotFoundError, "plan not found"):
        recurring.update(new_id(), save())


def test_changing_pausing_and_deleting(
    recurring: RecurringHandlers, store: Store, clock: FixedClock
) -> None:
    plan = recurring.create(save()).plan
    changed = recurring.update(
        plan.id, save(name="Hosting Plus", action=PlanAction.SEND, service_period=False)
    ).plan
    assert (changed.name, changed.action, changed.service_period) == (
        "Hosting Plus",
        PlanAction.SEND,
        False,
    )
    assert not recurring.pause(plan.id).plan.active
    at(clock, TODAY + timedelta(days=45))
    resumed = recurring.resume(plan.id).plan
    # Skipped while paused: 9 April; the next is 9 May.
    assert (resumed.active, resumed.next_date) == (True, date(2026, 5, 9))
    recurring.delete(plan.id)
    assert store.plans == {}


def test_an_issued_invoice_per_period(
    recurring: RecurringHandlers, documents: DocumentHandlers, store: Store, clock: FixedClock
) -> None:
    plan = recurring.create(save()).plan
    at(clock, TODAY - timedelta(days=1))
    assert recurring.run_due() == []
    at(clock, TODAY)
    [run] = recurring.run_due()
    assert (run.outcome, run.period_start, run.code, run.message) == (
        RunOutcome.ISSUED,
        TODAY,
        "",
        "",
    )
    assert run.document_id is not None
    invoice = documents.get(run.document_id).document
    assert invoice.status is DocumentStatus.ISSUED
    assert (invoice.content.service_from, invoice.content.service_to) == (
        TODAY,
        date(2026, 4, 8),
    )
    assert (invoice.content.subject, invoice.content.payment_text) == (
        "Hosting",
        "Zahlbar bis {faellig}.",
    )
    assert store.plans[plan.id].next_date == date(2026, 4, 9)
    # A second look the same day writes nothing more.
    assert recurring.run_due() == []
    assert recurring.get(plan.id).runs == (run,)
    assert store.runs == [run]


def test_drafts_and_no_service_period(
    recurring: RecurringHandlers, documents: DocumentHandlers
) -> None:
    recurring.create(save(action=PlanAction.DRAFT, service_period=False))
    [run] = recurring.run_due()
    assert run.outcome is RunOutcome.DRAFT
    assert run.document_id is not None
    draft = documents.get(run.document_id).document
    assert draft.is_draft
    assert (draft.content.service_from, draft.content.service_to) == (None, None)


def test_missed_periods_are_written_afterwards(
    recurring: RecurringHandlers, store: Store, clock: FixedClock
) -> None:
    plan = recurring.create(save(end_date=TODAY + timedelta(days=70))).plan
    at(clock, TODAY + timedelta(days=100))
    runs = recurring.run_due()
    # Three periods up to the end: 9 Mar, 9 Apr, 9 May; all dated today, each its period.
    assert [run.period_start for run in runs] == [
        date(2026, 3, 9),
        date(2026, 4, 9),
        date(2026, 5, 9),
    ]
    assert all(run.outcome is RunOutcome.ISSUED for run in runs)
    assert store.plans[plan.id].finished
    assert recurring.plans()[0].runs == (runs[-1],)


def test_a_long_downtime_is_caught_up_in_steps(
    recurring: RecurringHandlers, store: Store, clock: FixedClock
) -> None:
    plan = recurring.create(save(action=PlanAction.DRAFT)).plan
    at(clock, date(2028, 9, 9))
    # 31 periods are due: one look writes 24, the next the rest.
    assert len(recurring.run_due()) == 24
    assert store.plans[plan.id].next_date == date(2028, 3, 9)
    assert len(recurring.run_due()) == 7
    assert store.plans[plan.id].next_date == date(2028, 10, 9)


def test_a_period_is_written_once_only(recurring: RecurringHandlers, store: Store) -> None:
    plan = recurring.create(save()).plan
    # The period had its invoice before (the plan was restarted on the same day).
    other = PlanRun(plan.id, TODAY, NOW, RunOutcome.ISSUED, document_id=new_id())
    store.runs.append(other)
    assert recurring.run_due() == []
    # Not written twice, and the plan moves on instead of standing still.
    assert store.plans[plan.id].next_date == date(2026, 4, 9)
    assert store.runs == [other]


def test_after_a_period_written_before_the_next_ones_follow(
    recurring: RecurringHandlers, store: Store, clock: FixedClock
) -> None:
    plan = recurring.create(save()).plan
    store.runs.append(PlanRun(plan.id, TODAY, NOW, RunOutcome.ISSUED, document_id=new_id()))
    at(clock, date(2026, 4, 9))
    assert [run.period_start for run in recurring.run_due()] == [date(2026, 4, 9)]


def test_a_new_interval_on_the_day_of_an_invoice(
    recurring: RecurringHandlers, store: Store, clock: FixedClock
) -> None:
    plan = recurring.create(save()).plan
    [first] = recurring.run_due()
    recurring.update(plan.id, save(interval=Interval.QUARTERLY))
    assert store.plans[plan.id].next_date == TODAY
    # Today's invoice exists; the next comes a quarter later, and so on.
    assert recurring.run_due() == []
    assert store.plans[plan.id].next_date == date(2026, 6, 9)
    at(clock, date(2026, 6, 9))
    [second] = recurring.run_due()
    assert [run.period_start for run in (first, second)] == [TODAY, date(2026, 6, 9)]


class ArchiveFailsOnce(PrintHandlers):
    """The PDF service breaks down once, with an error nobody expected."""

    failed: ClassVar[list[UUID]] = []

    def archive(self, document_id: UUID) -> bool:
        if self.failed:
            return True
        self.failed.append(document_id)
        msg = "disk full"
        raise OSError(msg)


def test_an_unexpected_failure_keeps_the_invoice_and_the_other_plans(
    recurring: RecurringHandlers, caplog: pytest.LogCaptureFixture
) -> None:
    first = recurring.create(save(name="A")).plan
    second = recurring.create(save(name="B")).plan
    printing = recurring.printing
    failing = ArchiveFailsOnce(
        uow=printing.uow,
        clock=printing.clock,
        documents=printing.documents,
        renderer=printing.renderer,
    )
    ArchiveFailsOnce.failed.clear()
    broken, fine = replace(recurring, printing=failing).run_due()
    # Plans run in the order of their dates, then ids: the first one hit the failure.
    assert {broken.plan_id, fine.plan_id} == {first.id, second.id}
    assert (broken.code, broken.message) == ("unexpected_error", "disk full")
    # The invoice was created before the failure: the run still names it.
    assert (broken.outcome, broken.document_id) == (RunOutcome.DRAFT, failing.failed[0])
    assert recurring.get(broken.plan_id).runs == (broken,)
    # The other plan went on.
    assert (fine.outcome, fine.code) == (RunOutcome.ISSUED, "")
    assert "recurring invoice of plan" in caplog.text
    assert "disk full" in caplog.text


def test_a_plan_that_cannot_even_be_claimed(
    recurring: RecurringHandlers, store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    recurring.create(save())
    opened = 0

    def uow() -> InMemoryUnitOfWork:
        nonlocal opened
        opened += 1
        if opened == 2:
            msg = "connection lost"
            raise ConnectionError(msg)
        return InMemoryUnitOfWork(store)

    assert replace(recurring, uow=uow).run_due() == []
    assert "connection lost" in caplog.text


def test_the_run_logs_what_it_did(
    recurring: RecurringHandlers, store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    recurring.create(save())
    store.bank_accounts.clear()
    recurring.run_due()
    assert "recurring invoices: 1 written, 1 with problems" in caplog.text
    assert "bank_account_missing" in caplog.text


def test_a_plan_removed_while_running(recurring: RecurringHandlers, store: Store) -> None:
    recurring.create(save())
    opened = 0

    def uow() -> InMemoryUnitOfWork:
        nonlocal opened
        opened += 1
        if opened == 2:  # after looking for due plans, before taking the period
            store.plans.clear()
        return InMemoryUnitOfWork(store)

    assert replace(recurring, uow=uow).run_due() == []
    assert store.runs == []


def test_sending_to_the_customer(
    recurring: RecurringHandlers,
    mail: MailHandlers,
    documents: DocumentHandlers,
    sender: FakeSender,
) -> None:
    mail.save_server(
        SaveMailServer(
            host="smtp.example.com",
            port=587,
            security=MailSecurity.STARTTLS,
            sender="rechnung@muster.example",
        )
    )
    recurring.create(save(action=PlanAction.SEND))
    [run] = recurring.run_due()
    assert (run.outcome, run.code) == (RunOutcome.SENT, "")
    [(_, sent)] = sender.sent
    assert sent.to == (MAILBOX,)
    assert run.document_id is not None
    assert documents.get(run.document_id).document.events[-1].kind is EventKind.EMAILED


def test_what_keeps_an_invoice_from_going_out(
    recurring: RecurringHandlers,
    mail: MailHandlers,
    store: Store,
    clock: FixedClock,
    sender: FakeSender,
) -> None:
    plan = recurring.create(save(action=PlanAction.SEND)).plan
    # No mail server: issued, not sent.
    [unsent] = recurring.run_due()
    assert (unsent.outcome, unsent.code) == (RunOutcome.ISSUED, "mail_not_configured")
    assert unsent.message == "set up the mail server first (Settings → E-mail)"
    mail.save_server(
        SaveMailServer(
            host="smtp.example.com",
            port=587,
            security=MailSecurity.STARTTLS,
            sender="rechnung@muster.example",
        )
    )
    # The server refuses.
    sender.error = DeliveryError("the server refused the login", code="mail_auth_failed")
    at(clock, store.plans[plan.id].next_date)
    [refused] = recurring.run_due()
    assert (refused.outcome, refused.code) == (RunOutcome.ISSUED, "mail_auth_failed")
    assert refused.document_id is not None
    # No address at the customer.
    sender.error = None
    store.customers[CUSTOMER] = replace(store.customers[CUSTOMER], email=None)
    at(clock, store.plans[plan.id].next_date)
    [nowhere] = recurring.run_due()
    assert (nowhere.outcome, nowhere.code) == (RunOutcome.ISSUED, "customer_email_missing")
    assert nowhere.message == "the customer has no e-mail address; the invoice was not sent"
    assert sender.sent == []


def test_an_invoice_that_cannot_be_issued_stays_a_draft(
    recurring: RecurringHandlers, documents: DocumentHandlers, store: Store
) -> None:
    recurring.create(save())
    store.bank_accounts.clear()
    [run] = recurring.run_due()
    assert (run.outcome, run.code) == (RunOutcome.DRAFT, "bank_account_missing")
    assert run.document_id is not None
    assert documents.get(run.document_id).document.is_draft


def test_an_invoice_that_cannot_be_created(recurring: RecurringHandlers, store: Store) -> None:
    plan = recurring.create(save()).plan
    del store.customers[CUSTOMER]
    [run] = recurring.run_due()
    assert (run.outcome, run.document_id, run.code, run.message) == (
        RunOutcome.FAILED,
        None,
        "validation_error",
        "the customer does not exist",
    )
    # The period is done with; the next one is tried in a month.
    assert store.plans[plan.id].next_date == date(2026, 4, 9)
    assert recurring.get(plan.id).customer_name == ""


def test_a_total_that_cannot_be_calculated(recurring: RecurringHandlers, store: Store) -> None:
    lodging = replace(HOSTING, tax_category=TaxCategory.SPECIAL)
    plan = recurring.create(
        save(template=DraftInput(customer_id=CUSTOMER, currency=Currency.CHF, lines=(lodging,)))
    ).plan
    assert store.company is not None
    # Germany has no special rate.
    germany = factories.address(country=CountryCode("DE"))
    store.company = replace(store.company, address=germany)
    store.customers[CUSTOMER] = replace(store.customers[CUSTOMER], address=germany)
    assert recurring.get(plan.id).total is None


def test_a_plan_turns_into_the_invoice_it_was_given() -> None:
    draft = DraftInput(
        customer_id=CUSTOMER,
        currency=Currency.EUR,
        language=Language.EN,
        price_mode=PriceMode.GROSS,
        lines=(
            LineInput(kind=LineKind.TEXT, description="Monthly", details="ongoing"),
            LineInput(
                kind=LineKind.ITEM,
                description="Server",
                details="2 cores",
                quantity="1.5",
                unit="MON",
                unit_price="29.9",
                discount_percent="10",
                tax_category=TaxCategory.REDUCED,
                supply=Supply.GOODS,
                article_id=UUID(int=7),
            ),
        ),
        discount_kind=DiscountKind.AMOUNT,
        discount_value="5",
        subject="Hosting",
        reference="K-1",
        intro_text="Hello",
        payment_text="Payable",
        closing_text="Thanks",
    )
    plan = RecurringPlan.new(
        new_id(),
        name="Hosting",
        customer_id=CUSTOMER,
        interval=Interval.MONTHLY,
        start_date=TODAY,
        action=PlanAction.DRAFT,
        template=to_template(draft),
        today=TODAY,
        now=NOW,
    )
    # Text lines keep their default numbers; every other field comes back as given.
    text_line = replace(draft.lines[0], quantity="1", unit_price="0", discount_percent="0")
    assert plan_draft(plan) == replace(draft, lines=(text_line, draft.lines[1]))
    without_discount = replace(plan, template=replace(plan.template, discount=None))
    assert (
        plan_draft(without_discount).discount_kind,
        plan_draft(without_discount).discount_value,
    ) == (
        DiscountKind.PERCENT,
        None,
    )


def test_plans_are_locked_while_they_change(recurring: RecurringHandlers, store: Store) -> None:
    units: list[InMemoryUnitOfWork] = []

    def uow() -> InMemoryUnitOfWork:
        unit = InMemoryUnitOfWork(store)
        units.append(unit)
        return unit

    watched = replace(recurring, uow=uow)
    plan = watched.create(save()).plan
    assert plan.created_at == NOW

    def locked() -> list[UUID]:
        found = [plan_id for unit in units for plan_id in unit.recurring.locked]
        units.clear()
        return found

    locked()
    watched.update(plan.id, save(customer_id=CUSTOMER, end_date=date(2027, 1, 1)))
    assert locked() == [plan.id]
    assert store.plans[plan.id].end_date == date(2027, 1, 1)
    watched.pause(plan.id)
    assert locked() == [plan.id]
    watched.resume(plan.id)
    assert locked() == [plan.id]
    watched.run_due()
    # Taking a period locks the plan (once for the period, once to see none is left):
    # two processes never take the same one.
    assert locked() == [plan.id, plan.id]


def test_another_customer_for_a_plan(recurring: RecurringHandlers, store: Store) -> None:
    other = factories.customer(company_name="Andere AG")
    store.customers[other.id] = other
    plan = recurring.create(save()).plan
    changed = recurring.update(plan.id, save(customer_id=other.id))
    assert (changed.plan.customer_id, changed.customer_name) == (other.id, "Andere AG")


def test_the_period_is_marked_as_taken_while_it_is_written(
    recurring: RecurringHandlers, store: Store, clock: FixedClock
) -> None:
    plan = recurring.create(save()).plan
    clock.set(NOW + timedelta(minutes=3))
    seen: list[PlanRun] = []

    class Watching(DocumentHandlers):
        def create(self, document_type: DocumentType, draft: DraftInput) -> DocumentView:
            seen.extend(store.runs)
            return super().create(document_type, draft)

    documents = recurring.documents
    replace(recurring, documents=Watching(uow=documents.uow, clock=documents.clock)).run_due()
    # Until the invoice is written, the run says it was interrupted (should the process die).
    assert seen == [
        PlanRun(
            plan_id=plan.id,
            period_start=TODAY,
            at=NOW + timedelta(minutes=3),
            outcome=RunOutcome.FAILED,
            code="interrupted",
            message="the run stopped before the invoice was written",
        )
    ]


def test_the_logs_name_the_plan_and_what_went_wrong(
    recurring: RecurringHandlers, store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    plan = recurring.create(save()).plan
    store.bank_accounts.clear()
    recurring.run_due()
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        (
            f"recurring invoice of plan {plan.id} for {TODAY.isoformat()}: bank_account_missing"
            " (please add a bank account for CHF before issuing invoices in CHF)"
        ),
        "recurring invoices: 1 written, 1 with problems",
    ]


def test_an_error_without_words_is_named_by_its_kind(
    recurring: RecurringHandlers, store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    plan = recurring.create(save()).plan
    printing = recurring.printing

    class Silent(PrintHandlers):
        def archive(self, document_id: UUID) -> bool:
            del document_id
            # The plan goes away meanwhile, with its runs.
            store.plans.clear()
            store.runs.clear()
            raise OSError

    silent = Silent(
        uow=printing.uow,
        clock=printing.clock,
        documents=printing.documents,
        renderer=printing.renderer,
    )
    [run] = replace(recurring, printing=silent).run_due()
    assert (run.code, run.message, run.document_id) == ("unexpected_error", "OSError", None)
    assert [record.getMessage() for record in caplog.records if record.levelname == "ERROR"] == [
        f"recurring invoice of plan {plan.id} failed"
    ]


def test_a_failing_plan_is_named_in_the_log(
    recurring: RecurringHandlers, store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    plan = recurring.create(save()).plan
    opened = 0

    def uow() -> InMemoryUnitOfWork:
        nonlocal opened
        opened += 1
        if opened == 2:
            msg = "connection lost"
            raise ConnectionError(msg)
        return InMemoryUnitOfWork(store)

    replace(recurring, uow=uow).run_due()
    assert [record.getMessage() for record in caplog.records] == [
        f"recurring invoices of plan {plan.id} failed"
    ]


def test_plans_carry_their_bank_account(
    recurring: RecurringHandlers, store: Store, clock: FixedClock
) -> None:
    chosen = factories.bank_account(iban=Iban("CH5604835012345678009"))
    store.bank_accounts[chosen.id] = chosen
    template = replace(save().template, bank_account_id=chosen.id)
    plan = recurring.create(save(template=template, action=PlanAction.DRAFT)).plan
    assert plan.template.bank_account_id == chosen.id
    assert plan_draft(plan).bank_account_id == chosen.id
    [run] = recurring.run_due()
    assert run.document_id is not None
    assert store.documents[run.document_id].document.content.bank_account_id == chosen.id
    # Moved to another currency or deleted since: the next invoice is paid to the default.
    store.bank_accounts[chosen.id] = replace(chosen, currency=Currency.EUR)
    assert recurring.get(plan.id).total is not None
    del store.bank_accounts[chosen.id]
    assert recurring.get(plan.id).total is not None
    at(clock, TODAY + timedelta(days=31))
    [later] = recurring.run_due()
    assert later.document_id is not None
    assert store.documents[later.document_id].document.content.bank_account_id is None


def test_plans_check_their_bank_account(recurring: RecurringHandlers, store: Store) -> None:
    euros = factories.bank_account(currency=Currency.EUR, is_default=True)
    store.bank_accounts[euros.id] = euros
    wrong = replace(save().template, bank_account_id=euros.id)
    with raises_exactly(ValidationError, "the bank account is not in CHF"):
        recurring.create(save(template=wrong))
    plan = recurring.create(save()).plan
    with raises_exactly(ValidationError, "the bank account does not exist"):
        recurring.update(plan.id, save(template=replace(wrong, bank_account_id=new_id())))
    with raises_exactly(ValidationError, "a plan names its currency"):
        recurring.create(save(template=replace(wrong, currency=None)))
