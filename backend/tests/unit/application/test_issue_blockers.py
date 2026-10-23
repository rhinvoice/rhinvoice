"""The editor learns before issuing which company or customer details are still missing."""

from dataclasses import replace
from uuid import UUID

from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.money import Currency
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)
LINE = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="100")


def test_the_preview_lists_what_issuing_would_ask_for(store: Store, clock: FixedClock) -> None:
    store.company = factories.company(vat_number=None)
    store.customers[CUSTOMER] = factories.customer(id=CUSTOMER)
    documents = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    draft = DraftInput(customer_id=CUSTOMER, lines=(LINE,))
    assert documents.preview(DocumentType.INVOICE, draft).issue_blockers == (
        "bank_account_missing",
        "company_vat_number_missing",
    )
    # Quotes name no bank account and no tax IDs.
    assert documents.preview(DocumentType.QUOTE, draft).issue_blockers == ()
    account = factories.bank_account(is_default=True)
    store.bank_accounts[account.id] = account
    store.company = replace(store.company, vat_number=factories.company().vat_number)
    assert documents.preview(DocumentType.INVOICE, draft).issue_blockers == ()
    # The account must be in the invoice's currency.
    euros = replace(draft, currency=Currency.EUR)
    assert documents.preview(DocumentType.INVOICE, euros).issue_blockers == (
        "bank_account_missing",
    )
