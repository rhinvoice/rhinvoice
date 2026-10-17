from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import Field

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import (
    ERROR_RESPONSES,
    PERCENT_PATTERN,
    AddressSchema,
    ApiModel,
    SearchParams,
    plain_number,
    text,
)
from rhinvoice.application.customer.handlers import SaveCustomer
from rhinvoice.application.customer.ports import CustomerQuery, CustomerSort
from rhinvoice.domain.customer.customer import Customer, CustomerKind
from rhinvoice.domain.shared.email import EMAIL_PATTERN
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency

router = APIRouter(prefix="/api/customers", tags=["customers"], responses=ERROR_RESPONSES)


class CustomerRequest(ApiModel):
    kind: CustomerKind
    number: str = Field(default="", max_length=20, description="Empty: next number of the sequence")
    company_name: str = text(70)
    salutation: str = text(50)
    first_name: str = text(50)
    last_name: str = text(50)
    contact_person: str = text(70)
    address: AddressSchema
    delivery_address: AddressSchema | None = None
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_PATTERN)
    phone: str = text(50)
    vat_number: str | None = Field(default=None, max_length=40)
    buyer_reference: str = Field(
        default="",
        max_length=100,
        description="Leitweg-ID or fixed buyer reference for e-invoices (German customers)",
    )
    group: str = text(50)
    default_currency: Currency | None = None
    default_language: Language | None = None
    tax_exempt: bool = False
    default_discount: str = Field(default="0", pattern=PERCENT_PATTERN)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)
    note: str = text(4000)

    def to_command(self) -> SaveCustomer:
        return SaveCustomer(
            kind=self.kind,
            number=self.number,
            address=self.address.to_input(),
            company_name=self.company_name,
            salutation=self.salutation,
            first_name=self.first_name,
            last_name=self.last_name,
            contact_person=self.contact_person,
            email=self.email,
            phone=self.phone,
            vat_number=self.vat_number,
            buyer_reference=self.buyer_reference,
            group=self.group,
            default_currency=self.default_currency,
            default_language=self.default_language,
            tax_exempt=self.tax_exempt,
            default_discount=self.default_discount,
            payment_terms_days=self.payment_terms_days,
            delivery_address=None
            if self.delivery_address is None
            else self.delivery_address.to_input(),
            note=self.note,
        )


class CustomerResponse(ApiModel):
    id: UUID
    number: str
    kind: CustomerKind
    display_name: str
    company_name: str
    salutation: str
    first_name: str
    last_name: str
    contact_person: str
    address: AddressSchema
    delivery_address: AddressSchema | None
    email: str | None
    phone: str
    vat_number: str | None
    buyer_reference: str
    group: str
    default_currency: Currency | None
    default_language: Language | None
    tax_exempt: bool
    default_discount: str
    payment_terms_days: int | None
    note: str
    archived: bool
    created_at: datetime

    @classmethod
    def of(cls, customer: Customer) -> Self:
        return cls(
            id=customer.id,
            number=customer.number,
            kind=customer.kind,
            display_name=customer.display_name,
            company_name=customer.company_name,
            salutation=customer.salutation,
            first_name=customer.first_name,
            last_name=customer.last_name,
            contact_person=customer.contact_person,
            address=AddressSchema.of(customer.address),
            delivery_address=(
                None
                if customer.delivery_address is None
                else AddressSchema.of(customer.delivery_address)
            ),
            email=None if customer.email is None else str(customer.email),
            phone=customer.phone,
            vat_number=None if customer.vat_number is None else str(customer.vat_number),
            buyer_reference=customer.buyer_reference,
            group=customer.group,
            default_currency=customer.default_currency,
            default_language=customer.default_language,
            tax_exempt=customer.tax_exempt,
            default_discount=plain_number(customer.default_discount),
            payment_terms_days=customer.payment_terms_days,
            note=customer.note,
            archived=customer.archived,
            created_at=customer.created_at,
        )


class CustomerPage(ApiModel):
    items: list[CustomerResponse]
    total: int


class CustomerSearch(SearchParams):
    sort: CustomerSort = CustomerSort.NUMBER


@router.get("")
def search_customers(
    params: Annotated[CustomerSearch, Query()],
    _user: CurrentUser,
    container: ContainerDep,
) -> CustomerPage:
    page = container.customers.search(
        CustomerQuery(
            search=params.q,
            include_archived=params.include_archived,
            sort=params.sort,
            direction=params.direction,
            page=params.page_request(),
        ),
    )
    return CustomerPage(items=[CustomerResponse.of(c) for c in page.items], total=page.total)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_customer(
    body: CustomerRequest, _user: CurrentUser, container: ContainerDep
) -> CustomerResponse:
    return CustomerResponse.of(container.customers.create(body.to_command()))


@router.get("/{customer_id}")
def get_customer(
    customer_id: UUID, _user: CurrentUser, container: ContainerDep
) -> CustomerResponse:
    return CustomerResponse.of(container.customers.get(customer_id))


@router.put("/{customer_id}")
def update_customer(
    customer_id: UUID,
    body: CustomerRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> CustomerResponse:
    return CustomerResponse.of(container.customers.update(customer_id, body.to_command()))


@router.post("/{customer_id}/archive")
def archive_customer(
    customer_id: UUID, _user: CurrentUser, container: ContainerDep
) -> CustomerResponse:
    return CustomerResponse.of(container.customers.archive(customer_id))


@router.post("/{customer_id}/restore")
def restore_customer(
    customer_id: UUID, _user: CurrentUser, container: ContainerDep
) -> CustomerResponse:
    return CustomerResponse.of(container.customers.restore(customer_id))
