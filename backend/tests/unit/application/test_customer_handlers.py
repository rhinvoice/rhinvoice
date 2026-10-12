from datetime import date, timedelta
from decimal import Decimal

import pytest

from rhinvoice.application.common import AddressInput, PageRequest, SortDirection
from rhinvoice.application.customer.handlers import CustomerHandlers, SaveCustomer
from rhinvoice.application.customer.ports import CustomerQuery, CustomerSort
from rhinvoice.application.errors import ConflictError, NotFoundError
from rhinvoice.domain.customer.customer import CustomerKind
from rhinvoice.domain.numbering.sequence import NumberSequence, SequenceKind
from rhinvoice.domain.shared.clock import FixedClock
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.identifier import new_id
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.shared.money import Currency
from tests.helpers import raises_exactly
from tests.unit.application.conftest import NOW
from tests.unit.application.fakes import InMemoryUnitOfWork, Store

BERN = AddressInput(
    street="Marktgasse", house_number="5", postal_code="3011", city="Bern", country="CH"
)


@pytest.fixture
def handlers(store: Store, clock: FixedClock) -> CustomerHandlers:
    return CustomerHandlers(uow=lambda: InMemoryUnitOfWork(store), clock=clock)


def command(**overrides: object) -> SaveCustomer:
    values: dict[str, object] = {
        "kind": CustomerKind.COMPANY,
        "company_name": "Beispiel AG",
        "address": BERN,
    }
    values.update(overrides)
    return SaveCustomer(**values)  # type: ignore[arg-type]  # test builder


def test_create_assigns_numbers_from_the_sequence(handlers: CustomerHandlers, store: Store) -> None:
    first = handlers.create(command())
    second = handlers.create(command(company_name="Zweite AG"))
    assert (first.number, second.number) == ("1001", "1002")
    assert first.created_at == NOW
    assert store.sequences[SequenceKind.CUSTOMER].next_value == 1003


def test_create_with_all_fields(handlers: CustomerHandlers, store: Store) -> None:
    customer = handlers.create(
        command(
            kind=CustomerKind.PERSON,
            company_name="",
            salutation="Frau",
            first_name="Erika",
            last_name="Muster",
            contact_person="Assistenz",
            email="erika@example.com",
            phone="+41 79 000 00 00",
            vat_number="CHE-123.456.788",
            default_currency=Currency.EUR,
            default_language=Language.EN,
            tax_exempt=True,
            default_discount="5.5",
            payment_terms_days=10,
            delivery_address=AddressInput(postal_code="9490", city="Vaduz", country="LI"),
            note="VIP",
            group="Privat",
        ),
    )
    assert store.customers == {customer.id: customer}
    assert customer.kind is CustomerKind.PERSON
    assert customer.address.city == "Bern"
    assert (customer.salutation, customer.first_name, customer.last_name) == (
        "Frau",
        "Erika",
        "Muster",
    )
    assert customer.contact_person == "Assistenz"
    assert str(customer.email) == "erika@example.com"
    assert customer.phone == "+41 79 000 00 00"
    assert str(customer.vat_number) == "CHE-123.456.788"
    assert customer.group == "Privat"
    assert customer.default_currency is Currency.EUR
    assert customer.default_language is Language.EN
    assert customer.tax_exempt is True
    assert customer.default_discount == Decimal("5.5")
    assert customer.payment_terms_days == 10
    assert customer.delivery_address is not None
    assert customer.delivery_address.city == "Vaduz"
    assert customer.note == "VIP"
    assert customer.archived is False


def test_optional_fields_default_to_empty(handlers: CustomerHandlers) -> None:
    customer = handlers.create(command(vat_number=""))
    assert customer.vat_number is None
    assert customer.email is None
    assert customer.tax_exempt is False
    assert customer.default_currency is None
    assert customer.delivery_address is None


def test_empty_discount_means_zero(handlers: CustomerHandlers) -> None:
    assert handlers.create(command(default_discount="")).default_discount == 0


def test_manual_numbers_must_be_unique(handlers: CustomerHandlers) -> None:
    handlers.create(command(number=" 5000 "))
    with raises_exactly(ConflictError, "customer number 5000 is already taken") as error:
        handlers.create(command(number="5000"))
    assert error.value.details == {"number": "customer number 5000 is already taken"}


def test_automatic_numbers_skip_manually_used_ones(handlers: CustomerHandlers) -> None:
    handlers.create(command(number="1001"))
    handlers.create(command(number="1002"))
    assert handlers.create(command()).number == "1003"


def test_number_search_gives_up_eventually(handlers: CustomerHandlers, store: Store) -> None:
    for number in range(1001, 1101):
        handlers.create(command(number=str(number)))
    with raises_exactly(
        ConflictError, "no free customer number found, please check the number sequence"
    ):
        handlers.create(command())
    assert SequenceKind.CUSTOMER not in store.sequences


def test_update_keeps_number_creation_time_and_archive_flag(
    handlers: CustomerHandlers,
    clock: FixedClock,
    store: Store,
) -> None:
    created = handlers.create(command())
    handlers.archive(created.id)
    clock.set(NOW + timedelta(days=1))
    updated = handlers.update(created.id, command(company_name="Neu AG"))
    assert updated.number == created.number
    assert updated.created_at == NOW
    assert updated.archived
    assert updated.company_name == "Neu AG"
    assert updated.id == created.id
    assert store.customers[created.id] == updated
    assert len(store.customers) == 1
    renumbered = handlers.update(created.id, command(number="77"))
    assert renumbered.number == "77"


def test_update_rejects_taken_numbers_and_unknown_ids(handlers: CustomerHandlers) -> None:
    first = handlers.create(command())
    second = handlers.create(command())
    with raises_exactly(ConflictError, f"customer number {first.number} is already taken"):
        handlers.update(second.id, command(number=first.number))
    handlers.update(first.id, command(number=first.number))
    with raises_exactly(NotFoundError, "customer not found"):
        handlers.update(new_id(), command())
    with raises_exactly(NotFoundError, "customer not found"):
        handlers.get(new_id())
    with raises_exactly(NotFoundError, "customer not found"):
        handlers.archive(new_id())


def test_archive_and_restore(handlers: CustomerHandlers, store: Store) -> None:
    customer = handlers.create(command())
    assert handlers.archive(customer.id).archived is True
    assert store.customers[customer.id].archived is True
    assert handlers.restore(customer.id).archived is False
    assert handlers.get(customer.id).archived is False


def test_invalid_input_is_rejected_without_side_effects(
    handlers: CustomerHandlers, store: Store
) -> None:
    with pytest.raises(ValidationError):
        handlers.create(command(company_name=""))
    with pytest.raises(ValidationError) as discount:
        handlers.create(command(default_discount="abc"))
    assert discount.value.field == "default_discount"
    assert store.customers == {}


def test_search_filters_sorts_and_pages(handlers: CustomerHandlers) -> None:
    mueller = handlers.create(command(company_name="Müller AG"))
    zebra = handlers.create(
        command(
            company_name="Zebra GmbH",
            address=AddressInput(postal_code="1", city="Aarau", country="CH"),
        )
    )
    archived = handlers.create(command(company_name="Alt AG"))
    handlers.archive(archived.id)

    found = handlers.search(CustomerQuery(search="muller"))
    assert [c.id for c in found.items] == [mueller.id]
    spelled = handlers.search(CustomerQuery(search="Mueller"))
    assert [c.id for c in spelled.items] == [mueller.id]
    assert found.total == 1
    all_active = handlers.search(
        CustomerQuery(sort=CustomerSort.NAME, direction=SortDirection.DESC)
    )
    assert [c.id for c in all_active.items] == [zebra.id, mueller.id]
    with_archived = handlers.search(CustomerQuery(include_archived=True, sort=CustomerSort.CITY))
    assert [c.id for c in with_archived.items] == [zebra.id, mueller.id, archived.id]
    paged = handlers.search(
        CustomerQuery(include_archived=True, page=PageRequest(limit=1, offset=1))
    )
    assert paged.total == 3
    assert [c.id for c in paged.items] == [zebra.id]


def test_existing_sequence_configuration_is_used(handlers: CustomerHandlers, store: Store) -> None:
    store.sequences[SequenceKind.CUSTOMER] = NumberSequence.default(
        SequenceKind.CUSTOMER
    ).reconfigure(
        pattern="K{NNNN}",
        start_value=1,
        yearly_reset=False,
        next_value=7,
        on=date(2026, 1, 1),
    )
    assert handlers.create(command()).number == "K0007"
