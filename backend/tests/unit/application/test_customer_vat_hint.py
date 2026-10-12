"""The editor learns when an EU business customer lacks the VAT number for reverse charge."""

from dataclasses import replace
from uuid import UUID

from rhinvoice.application.document.handlers import DocumentHandlers, DraftInput, LineInput
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.document.lines import LineKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.tax.vat_number import VatNumber
from tests.unit.application.fakes import InMemoryUnitOfWork, Store
from tests.unit.domain import factories

CUSTOMER = UUID(int=1)
LINE = LineInput(kind=LineKind.ITEM, description="Beratung", quantity="1", unit_price="100")


def test_the_preview_says_when_the_vat_number_is_missing(store: Store, clock: FixedClock) -> None:
    store.company = factories.company()
    austrian = factories.customer(
        id=CUSTOMER,
        address=factories.address(postal_code="6850", city="Dornbirn", country=CountryCode("AT")),
    )
    store.customers[CUSTOMER] = austrian
    documents = DocumentHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)
    draft = DraftInput(customer_id=CUSTOMER, lines=(LINE,))
    preview = documents.preview(DocumentType.INVOICE, draft)
    assert preview.customer_vat_missing
    assert preview.view.document.content.treatment is TaxTreatment.EXPORT
    overridden = replace(draft, treatment_override=TaxTreatment.REVERSE_CHARGE, override_reason="x")
    assert not documents.preview(DocumentType.INVOICE, overridden).customer_vat_missing
    store.customers[CUSTOMER] = factories.customer(
        id=CUSTOMER, address=austrian.address, vat_number=VatNumber.parse("ATU12345678")
    )
    preview = documents.preview(DocumentType.INVOICE, draft)
    assert not preview.customer_vat_missing
    assert preview.view.document.content.treatment is TaxTreatment.REVERSE_CHARGE
