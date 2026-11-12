"""Several named print layouts, one the default, chosen per customer or document (#48)."""

from uuid import UUID

import pytest

from rhinvoice.domain.company.print_layout import (
    NamedLayout,
    PrintLayout,
    PrintTemplate,
    default_layout,
    layout_for,
)
from rhinvoice.domain.shared.errors import InvalidStateError, ValidationError
from tests.helpers import raises_exactly

STANDARD = NamedLayout(UUID(int=1), " Standard ", PrintLayout(), is_default=True)
TRUST = NamedLayout(UUID(int=2), "Treuhand", PrintLayout(template=PrintTemplate.CLASSIC))
PLAIN = NamedLayout(UUID(int=3), "Schlicht", PrintLayout(template=PrintTemplate.PLAIN))
LAYOUTS = (TRUST, STANDARD, PLAIN)
GONE = UUID(int=9)


def test_a_layout_has_a_name() -> None:
    assert STANDARD.name == "Standard"
    assert not TRUST.is_default
    assert NamedLayout(UUID(int=4), "x" * 60, PrintLayout()).name == "x" * 60


@pytest.mark.parametrize(
    ("name", "message"),
    [("", "name is required"), ("x" * 61, "name must be at most 60 characters long")],
)
def test_a_name_is_required_and_short(name: str, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        NamedLayout(UUID(int=4), name, PrintLayout())
    assert error.value.details == {"name": message}


def test_the_document_s_choice_wins_then_the_customer_s_then_the_default() -> None:
    assert layout_for(LAYOUTS, PLAIN.id, TRUST.id) == PLAIN
    assert layout_for(LAYOUTS, None, TRUST.id) == TRUST
    assert layout_for(LAYOUTS, None, None) == STANDARD
    # A deleted layout falls through to the next choice.
    assert layout_for(LAYOUTS, GONE, TRUST.id) == TRUST
    assert layout_for(LAYOUTS, GONE, GONE) == STANDARD


def test_there_is_always_a_default() -> None:
    assert default_layout(LAYOUTS) == STANDARD
    with raises_exactly(InvalidStateError, "there is no default print layout"):
        default_layout((TRUST, PLAIN))
