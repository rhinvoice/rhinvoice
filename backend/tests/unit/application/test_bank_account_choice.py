"""The bank account a document is paid to: chosen per document, else the default."""

from dataclasses import replace
from uuid import UUID

import pytest

from rhinvoice.application.common import AddressInput
from rhinvoice.application.company.handlers import CompanyHandlers, SaveBankAccount
from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.application.document.printing import PrintHandlers
from rhinvoice.domain.company.bank_account import BankAccount
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.iban import Iban
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import Currency
from rhinvoice.infrastructure.rendering.html import JinjaDocumentRenderer
from tests.helpers import raises_exactly
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories
from tests.unit.domain.factories import CH_IBAN

CUSTOMER = UUID(int=1)
SECOND_CH_IBAN = "CH5604835012345678009"
HOURS = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="2", unit_price="150")


@pytest.fixture
def own(store: Store) -> BankAccount:
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    return account


@pytest.fixture
def provider(store: Store) -> BankAccount:
    account = factories.bank_account(
        iban=Iban(SECOND_CH_IBAN),
        holder="Inkasso AG",
        third_party=True,
        holder_address=factories.address(street="Zahlweg", city="Basel", postal_code="4001"),
    )
    store.bank_accounts[account.id] = account
    return account


@pytest.fixture
def documents(store: Store, clock: FixedClock, own: BankAccount) -> DocumentHandlers:
    del own
    store.company = factories.company()
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    return DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


@pytest.fixture
def printing(store: Store, clock: FixedClock, documents: DocumentHandlers) -> PrintHandlers:
    return PrintHandlers(
        uow=lambda: InMemoryUnitOfWork(store),
        clock=clock,
        documents=documents,
        renderer=JinjaDocumentRenderer(),
    )


def draft(**overrides: object) -> DraftInput:
    values: dict[str, object] = {"customer_id": CUSTOMER, "lines": (HOURS,)}
    values.update(overrides)
    return DraftInput(**values)  # type: ignore[arg-type]  # test builder


def test_without_a_choice_the_default_account_is_paid(
    documents: DocumentHandlers, printing: PrintHandlers, own: BankAccount, provider: BankAccount
) -> None:
    del provider
    view = documents.create(DocumentType.INVOICE, draft())
    assert view.document.content.bank_account_id is None
    assert printing.model(view).bank_account == own
    issued = documents.issue(view.document.id).document
    assert issued.issued_snapshot.bank_account == own


def test_the_chosen_account_is_kept_printed_and_frozen(
    documents: DocumentHandlers, printing: PrintHandlers, provider: BankAccount
) -> None:
    view = documents.create(DocumentType.INVOICE, draft(bank_account_id=provider.id))
    assert view.document.content.bank_account_id == provider.id
    assert printing.model(view).bank_account == provider
    preview = documents.preview(DocumentType.QUOTE, draft(bank_account_id=provider.id))
    assert printing.model(preview.view).bank_account == provider
    updated = documents.update(view.document.id, draft(bank_account_id=provider.id))
    assert updated.document.content.bank_account_id == provider.id
    issued = documents.issue(view.document.id).document
    assert issued.issued_snapshot.bank_account == provider


def test_the_chosen_account_must_exist_in_the_currency(
    documents: DocumentHandlers, store: Store
) -> None:
    with raises_exactly(ValidationError, "the bank account does not exist") as unknown:
        documents.create(DocumentType.INVOICE, draft(bank_account_id=new_id()))
    assert (unknown.value.field, unknown.value.code) == ("bank_account_id", "bank_account_unknown")
    euros = factories.bank_account(currency=Currency.EUR, is_default=True)
    store.bank_accounts[euros.id] = euros
    with raises_exactly(ValidationError, "the bank account is not in CHF") as other:
        documents.preview(DocumentType.INVOICE, draft(bank_account_id=euros.id))
    assert other.value.code == "bank_account_currency"


def test_a_deleted_choice_falls_back_to_the_default(
    documents: DocumentHandlers,
    printing: PrintHandlers,
    store: Store,
    own: BankAccount,
    provider: BankAccount,
) -> None:
    view = documents.create(DocumentType.INVOICE, draft(bank_account_id=provider.id))
    CompanyHandlers(uow=lambda: InMemoryUnitOfWork(store)).delete_bank_account(provider.id)
    assert printing.model(documents.get(view.document.id)).bank_account == own
    issued = documents.issue(view.document.id).document
    assert issued.issued_snapshot.bank_account == own


def test_issue_blockers_look_at_the_paying_account(
    documents: DocumentHandlers, store: Store, own: BankAccount
) -> None:
    del store.bank_accounts[own.id]
    euros = factories.bank_account(currency=Currency.EUR)
    store.bank_accounts[euros.id] = euros
    blocked = documents.preview(DocumentType.INVOICE, draft(currency=Currency.EUR))
    assert "bank_account_missing" in blocked.issue_blockers
    chosen = documents.preview(
        DocumentType.INVOICE, draft(currency=Currency.EUR, bank_account_id=euros.id)
    )
    assert "bank_account_missing" not in chosen.issue_blockers


def test_third_party_accounts_are_saved_with_the_holders_address(store: Store) -> None:
    handlers = CompanyHandlers(uow=lambda: InMemoryUnitOfWork(store))
    address = AddressInput(street="Zahlweg", postal_code="4001", city="Basel", country="ch")
    command = SaveBankAccount(
        currency=Currency.CHF,
        bank_name="Bank",
        holder="Inkasso AG",
        iban=CH_IBAN,
        third_party=True,
        holder_address=address,
    )
    account = handlers.create_bank_account(command)
    assert account.third_party
    assert account.holder_address == factories.address(
        street="Zahlweg", house_number="", postal_code="4001", city="Basel"
    )
    assert account.holder_address is not None
    assert account.holder_address.country == CountryCode("CH")
    own = handlers.update_bank_account(account.id, replace(command, third_party=False))
    assert (own.third_party, own.holder_address) == (False, None)
    with raises_exactly(ValidationError, "a third party's account needs the holder's address"):
        handlers.create_bank_account(replace(command, holder_address=None))
