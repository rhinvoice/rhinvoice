"""Use cases for customers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING

from rhinvoice.application.common import AddressInput, optional_email, optional_vat_number
from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.application.numbering.handlers import allocate_number
from rhinvoice.domain.customer.customer import Customer, CustomerKind
from rhinvoice.domain.numbering.sequence import SequenceKind
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.money import parse_decimal

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from rhinvoice.application.common import Page
    from rhinvoice.application.customer.ports import CustomerQuery
    from rhinvoice.application.uow import UnitOfWork, UnitOfWorkFactory
    from rhinvoice.domain.shared.clock import Clock
    from rhinvoice.domain.shared.language import Language
    from rhinvoice.domain.shared.money import Currency

MAX_NUMBER_ATTEMPTS = 100


@dataclass(frozen=True, slots=True)
class SaveCustomer:
    kind: CustomerKind
    address: AddressInput
    number: str = ""
    """Empty: take the next number of the customer sequence."""
    company_name: str = ""
    salutation: str = ""
    first_name: str = ""
    last_name: str = ""
    contact_person: str = ""
    email: str | None = None
    phone: str = ""
    vat_number: str | None = None
    buyer_reference: str = ""
    """Leitweg-ID or another fixed buyer reference for e-invoices (German customers)."""
    group: str = ""
    default_currency: Currency | None = None
    default_language: Language | None = None
    tax_exempt: bool = False
    default_discount: str = "0"
    payment_terms_days: int | None = None
    delivery_address: AddressInput | None = None
    note: str = ""
    customer_since: date | None = None
    """When the customer relationship began, e.g. from the old program; kept otherwise."""


@dataclass(frozen=True, slots=True)
class CustomerHandlers:
    uow: UnitOfWorkFactory
    clock: Clock

    def search(self, query: CustomerQuery) -> Page[Customer]:
        with self.uow() as uow:
            return uow.customers.search(query)

    def get(self, customer_id: UUID) -> Customer:
        with self.uow() as uow:
            return self._require(uow, customer_id)

    def create(self, command: SaveCustomer) -> Customer:
        with self.uow() as uow:
            number = command.number.strip() or next_free_customer_number(uow, self.clock.today())
            customer = build_customer(
                new_id(), number, command, now=self.clock.now(), existing=None
            )
            self._ensure_unique(uow, customer.number, exclude_id=None)
            uow.customers.add(customer)
            uow.commit()
        return customer

    def update(self, customer_id: UUID, command: SaveCustomer) -> Customer:
        with self.uow() as uow:
            existing = self._require(uow, customer_id)
            number = command.number.strip() or existing.number
            customer = build_customer(
                customer_id, number, command, now=self.clock.now(), existing=existing
            )
            self._ensure_unique(uow, customer.number, exclude_id=customer_id)
            uow.customers.update(customer)
            uow.commit()
        return customer

    def archive(self, customer_id: UUID) -> Customer:
        return self._change(customer_id, Customer.archive)

    def restore(self, customer_id: UUID) -> Customer:
        return self._change(customer_id, Customer.restore)

    def _change(self, customer_id: UUID, change: Callable[[Customer], Customer]) -> Customer:
        with self.uow() as uow:
            customer = change(self._require(uow, customer_id))
            uow.customers.update(customer)
            uow.commit()
        return customer

    @staticmethod
    def _ensure_unique(uow: UnitOfWork, number: str, *, exclude_id: UUID | None) -> None:
        if uow.customers.number_exists(number, exclude_id=exclude_id):
            message = f"customer number {number} is already taken"
            raise ConflictError(message, details={"number": message})

    @staticmethod
    def _require(uow: UnitOfWork, customer_id: UUID) -> Customer:
        customer = uow.customers.get(customer_id)
        if customer is None:
            raise NotFoundError("customer not found")
        return customer


def _created_at(command: SaveCustomer, *, now: datetime, existing: Customer | None) -> datetime:
    since = command.customer_since
    if since is None:
        return now if existing is None else existing.created_at
    if since > now.date():
        raise ValidationError("customer_since", "the date lies in the future")
    return datetime.combine(since, time(), tzinfo=UTC)


def build_customer(
    customer_id: UUID,
    number: str,
    command: SaveCustomer,
    *,
    now: datetime,
    existing: Customer | None,
) -> Customer:
    """Build the customer of a create or update command; raise ValidationError if invalid."""
    return Customer(
        id=customer_id,
        number=number,
        kind=command.kind,
        address=command.address.to_domain(),
        created_at=_created_at(command, now=now, existing=existing),
        company_name=command.company_name,
        salutation=command.salutation,
        first_name=command.first_name,
        last_name=command.last_name,
        contact_person=command.contact_person,
        email=optional_email(command.email),
        phone=command.phone,
        vat_number=optional_vat_number(command.vat_number),
        buyer_reference=command.buyer_reference,
        group=command.group,
        default_currency=command.default_currency,
        default_language=command.default_language,
        tax_exempt=command.tax_exempt,
        default_discount=parse_decimal(command.default_discount or "0", "default_discount"),
        payment_terms_days=command.payment_terms_days,
        delivery_address=(
            None if command.delivery_address is None else command.delivery_address.to_domain()
        ),
        note=command.note,
        archived=False if existing is None else existing.archived,
    )


def next_free_customer_number(uow: UnitOfWork, today: date) -> str:
    """Take the next number of the sequence, skipping numbers assigned manually."""
    for _ in range(MAX_NUMBER_ATTEMPTS):
        number = allocate_number(uow, SequenceKind.CUSTOMER, today)
        if not uow.customers.number_exists(number):
            return number
    raise ConflictError("no free customer number found, please check the number sequence")
