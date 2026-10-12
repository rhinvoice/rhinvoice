import pytest

from rhinvoice.application.common import (
    AddressInput,
    Page,
    PageRequest,
    optional_email,
    optional_vat_number,
)
from rhinvoice.domain.shared.errors import ValidationError


def test_address_input_to_domain() -> None:
    address = AddressInput(
        postal_code="8001", city="Zürich", country=" ch ", street="A", house_number="1"
    )
    domain = address.to_domain()
    assert domain.country.value == "CH"
    assert domain.street_line == "A 1"
    assert (
        AddressInput(postal_code="1", city="X", country="DE", supplement="c/o")
        .to_domain()
        .supplement
        == "c/o"
    )


def test_optional_value_parsers() -> None:
    assert optional_email(None) is None
    assert optional_email("  ") is None
    assert str(optional_email(" Anna@Example.com")) == "anna@example.com"
    assert optional_vat_number(None) is None
    assert optional_vat_number("") is None
    assert str(optional_vat_number("de123456789")) == "DE123456789"


def test_page_request_bounds() -> None:
    assert PageRequest().limit == 50
    assert PageRequest(limit=1, offset=0).offset == 0
    assert PageRequest(limit=200).limit == 200
    with pytest.raises(ValidationError) as low:
        PageRequest(limit=0)
    assert low.value.details == {"limit": "limit must be between 1 and 200"}
    with pytest.raises(ValidationError):
        PageRequest(limit=201)
    with pytest.raises(ValidationError) as negative:
        PageRequest(offset=-1)
    assert negative.value.details == {"offset": "offset must not be negative"}


def test_page() -> None:
    page = Page(items=[1, 2], total=5)
    assert page.items == [1, 2]
    assert page.total == 5
