"""The facts next to the address: rows a layout shows or hides, fields with values (#62, #60)."""

from dataclasses import replace

import pytest

from rhinvoice.domain.company.print_layout import (
    DEFAULT_INFO_BLOCK,
    InfoEntry,
    InfoField,
    InfoRow,
    PrintLayout,
    is_field_key,
)
from rhinvoice.domain.document.document import FieldValue
from rhinvoice.domain.document.lines import PriceMode
from rhinvoice.domain.recurring.plan import InvoiceTemplate
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.money import Currency
from tests.unit.domain.test_document import content, line

COST_CENTRE = InfoEntry(InfoField.BUYER_ACCOUNTING.value)
OWN = InfoEntry("custom-0a1b2c3d", label=" Objekt ")


def refused(field: str, message: str) -> pytest.RaisesExc[ValidationError]:
    """Expect a ValidationError naming exactly this field and message."""
    return pytest.raises(ValidationError, check=lambda error: error.details == {field: message})


def block(*extra: InfoEntry) -> tuple[InfoEntry, ...]:
    return (*DEFAULT_INFO_BLOCK, *extra)


def test_the_default_block_shows_every_row_in_the_old_order() -> None:
    layout = PrintLayout()
    assert [entry.key for entry in layout.info_block] == [row.value for row in InfoRow]
    assert all(layout.shows(row) for row in InfoRow)
    assert layout.field_keys == ()


def test_rows_can_be_hidden_and_reordered_fields_added() -> None:
    hidden = InfoEntry(InfoRow.SERVICE_DATE.value, shown=False)
    entries = (
        InfoEntry(InfoRow.NUMBER.value),
        COST_CENTRE,
        InfoEntry(InfoRow.DATE.value),
        InfoEntry(InfoRow.CUSTOMER_NUMBER.value),
        InfoEntry(InfoRow.DUE_DATE.value),
        hidden,
        OWN,
        InfoEntry(InfoRow.REFERENCE.value),
    )
    layout = PrintLayout(info_block=entries)
    assert not layout.shows(InfoRow.SERVICE_DATE)
    assert layout.shows(InfoRow.REFERENCE)
    assert layout.field_keys == ("buyer_accounting", "custom-0a1b2c3d")
    assert OWN.label == "Objekt"
    assert (OWN.is_field, COST_CENTRE.is_field, hidden.is_field) == (True, True, False)


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"key": "number", "shown": False}, "the row number is always shown"),
        ({"key": "date", "shown": False}, "the row date is always shown"),
        ({"key": "reference", "label": "Ref"}, "only custom fields take a label"),
        ({"key": "project", "label": "Projekt"}, "only custom fields take a label"),
        ({"key": "project", "shown": False}, "a field is removed, not hidden"),
        ({"key": "custom-0a1b2c3d", "shown": False}, "a field is removed, not hidden"),
        ({"key": "custom-0a1b2c3d"}, "info_block is required"),
        (
            {"key": "custom-0a1b2c3d", "label": "x" * 41},
            "info_block must be at most 40 characters long",
        ),
        ({"key": "custom-XYZ"}, "unknown row custom-XYZ"),
        ({"key": "iban"}, "unknown row iban"),
    ],
)
def test_an_entry_names_a_row_or_a_field(entry: dict[str, object], message: str) -> None:
    with refused("info_block", message):
        InfoEntry(**entry)  # type: ignore[arg-type]  # test builder


def test_rows_may_be_hidden_unless_required() -> None:
    for row in (InfoRow.CUSTOMER_NUMBER, InfoRow.DUE_DATE, InfoRow.SERVICE_DATE, InfoRow.REFERENCE):
        assert not InfoEntry(row.value, shown=False).shown
    assert InfoEntry("custom-0a1b2c3d", label="x" * 40).label == "x" * 40


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        (block(COST_CENTRE, COST_CENTRE), "each row appears once"),
        (DEFAULT_INFO_BLOCK[1:], "every row is listed, shown or hidden"),
        (
            block(
                *(InfoEntry(field.value) for field in InfoField),
                *(InfoEntry(f"custom-0000000{index}", label="Feld") for index in range(10)),
                InfoEntry("custom-000000aa", label="Feld"),
            ),
            "at most 24 rows",
        ),
    ],
)
def test_a_block_lists_every_row_once(entries: tuple[InfoEntry, ...], message: str) -> None:
    with refused("info_block", message):
        PrintLayout(info_block=entries)


def test_a_block_holds_every_reference_and_ten_own_fields() -> None:
    entries = block(
        *(InfoEntry(field.value) for field in InfoField),
        *(InfoEntry(f"custom-0000000{index}", label="Feld") for index in range(10)),
    )
    assert len(PrintLayout(info_block=entries).field_keys) == 18


def test_field_keys() -> None:
    assert all(is_field_key(field.value) for field in InfoField)
    assert is_field_key("custom-0a1b2c3d")
    assert not is_field_key("custom-0a1b2c3")
    assert not is_field_key("custom-0a1b2c3d0")
    assert not is_field_key("number")


def test_documents_keep_the_values_of_fields() -> None:
    draft = content(
        fields=(
            FieldValue("project", " Website "),
            FieldValue("custom-0a1b2c3d", ""),
            FieldValue("buyer_accounting", "CC-100"),
        )
    )
    assert draft.fields == (
        FieldValue("project", "Website"),
        FieldValue("buyer_accounting", "CC-100"),
    )
    assert draft.field("project") == "Website"
    assert draft.field("custom-0a1b2c3d") == ""


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ((FieldValue("project", "A"), FieldValue("project", "B")), "each field appears once"),
        (
            tuple(FieldValue(f"custom-000000{index:02x}", "x") for index in range(25)),
            "at most 24 fields",
        ),
    ],
)
def test_a_field_has_one_value(fields: tuple[FieldValue, ...], message: str) -> None:
    with refused("fields", message):
        content(fields=fields)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("number", "1", "unknown field number"),
        ("project", "x" * 101, "fields must be at most 100 characters long"),
        ("project", "a\nb", "fields must not contain line breaks or control characters"),
    ],
)
def test_a_value_belongs_to_a_field(key: str, value: str, message: str) -> None:
    with refused("fields", message):
        FieldValue(key, value)


def test_values_of_a_hundred_characters_and_two_dozen_fields_fit() -> None:
    fields = tuple(FieldValue(f"custom-000000{index:02x}", "x" * 100) for index in range(24))
    assert len(content(fields=fields).fields) == 24


def test_recurring_invoices_carry_the_values() -> None:
    template = InvoiceTemplate(
        currency=Currency.CHF,
        price_mode=PriceMode.NET,
        lines=(line(),),
        fields=(FieldValue("contract", " V-7 "), FieldValue("project", "")),
    )
    assert template.fields == (FieldValue("contract", "V-7"),)
    with refused("fields", "each field appears once"):
        replace(template, fields=(FieldValue("contract", "1"), FieldValue("contract", "2")))
