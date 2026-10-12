"""The checklist of a new installation follows from the data."""

from datetime import timedelta
from uuid import UUID

import pytest

from rhinvoice.application.backup.ports import BackupReason, BackupRun, RunStatus
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.onboarding.handlers import OnboardingHandlers, OnboardingStep
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)


@pytest.fixture
def handlers(store: Store, clock: FixedClock) -> OnboardingHandlers:
    return OnboardingHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


def done(handlers: OnboardingHandlers) -> dict[OnboardingStep, bool]:
    return dict(handlers.status().steps)


def run(status: RunStatus) -> BackupRun:
    return BackupRun(
        id=1,
        started_at=NOW,
        finished_at=NOW,
        reason=BackupReason.DAILY,
        status=status,
        snapshot_id=None,
        data_added=None,
        message=None,
    )


def test_a_new_installation_has_everything_to_do(handlers: OnboardingHandlers) -> None:
    status = handlers.status()
    assert [step for step, _ in status.steps] == list(OnboardingStep)
    assert not any(finished for _, finished in status.steps)
    assert not status.dismissed
    assert not status.complete


def test_steps_are_done_when_the_data_is_there(
    handlers: OnboardingHandlers, store: Store, clock: FixedClock
) -> None:
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    assert done(handlers) == {
        OnboardingStep.COMPANY: True,
        OnboardingStep.BANK_ACCOUNT: True,
        OnboardingStep.NUMBERING: False,
        OnboardingStep.CUSTOMERS: False,
        OnboardingStep.FIRST_INVOICE: False,
        OnboardingStep.BACKUP: False,
    }
    # Archived customers count, too: the customers are there.
    customer = factories.customer(id=CUSTOMER, archived=True)
    store.customers[customer.id] = customer
    assert done(handlers)[OnboardingStep.CUSTOMERS]
    store.customers[customer.id] = factories.customer(id=CUSTOMER)
    documents = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    line = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="10")
    documents.create(DocumentType.QUOTE, DraftInput(customer_id=CUSTOMER, lines=(line,)))
    # A quote is not the first invoice.
    assert not done(handlers)[OnboardingStep.FIRST_INVOICE]
    draft = documents.create(
        DocumentType.INVOICE, DraftInput(customer_id=CUSTOMER, lines=(line,))
    ).document.id
    # A draft is not yet the first invoice.
    assert not done(handlers)[OnboardingStep.FIRST_INVOICE]
    documents.issue(draft)
    assert done(handlers)[OnboardingStep.FIRST_INVOICE]


def test_the_backup_step_needs_a_successful_backup(
    handlers: OnboardingHandlers, store: Store
) -> None:
    store.backup_runs = [run(RunStatus.NOT_CONFIGURED), run(RunStatus.FAILED)]
    assert not done(handlers)[OnboardingStep.BACKUP]
    store.backup_runs = [run(RunStatus.SUCCEEDED), run(RunStatus.FAILED)]
    assert done(handlers)[OnboardingStep.BACKUP]


def test_checking_the_numbering_and_hiding_the_list_are_remembered(
    handlers: OnboardingHandlers, store: Store
) -> None:
    status = handlers.check_numbering()
    assert dict(status.steps)[OnboardingStep.NUMBERING]
    assert store.numbering_checked_at == NOW
    later = OnboardingHandlers(
        uow=lambda: InMemoryUnitOfWork(store), clock=FixedClock(NOW + timedelta(days=1))
    )
    later.check_numbering()
    assert store.numbering_checked_at == NOW
    assert later.dismiss().dismissed
    assert not later.show().dismissed
    assert store.onboarding_dismissed_at is None
    later.dismiss()
    assert store.onboarding_dismissed_at == NOW + timedelta(days=1)
    assert handlers.status().dismissed


def test_the_list_is_complete_when_every_step_is_done(
    handlers: OnboardingHandlers, store: Store, clock: FixedClock
) -> None:
    store.company = factories.company()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    customer = factories.customer(id=CUSTOMER)
    store.customers[customer.id] = customer
    line = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="10")
    documents = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    documents.issue(
        documents.create(
            DocumentType.INVOICE, DraftInput(customer_id=CUSTOMER, lines=(line,))
        ).document.id
    )
    store.backup_runs = [run(RunStatus.SUCCEEDED)]
    assert not handlers.status().complete
    assert handlers.check_numbering().complete
