import pytest

from rhinvoice.domain.shared.address import Address
from rhinvoice.domain.shared.country import CountryCode
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.text import clean_multiline, clean_text

CH = CountryCode("CH")


def test_clean_text() -> None:
    assert clean_text("  Muster AG ", "name", max_length=20) == "Muster AG"
    assert clean_text("", "name", max_length=5) == ""
    assert clean_text("abcde", "name", max_length=5) == "abcde"
    with pytest.raises(ValidationError) as missing:
        clean_text("   ", "name", max_length=5, required=True)
    assert missing.value.details == {"name": "name is required"}
    with pytest.raises(ValidationError) as long:
        clean_text("abcdef", "name", max_length=5)
    assert long.value.details == {"name": "name must be at most 5 characters long"}


def test_clean_multiline() -> None:
    assert clean_multiline(" a  \r\nb\rc \n", "note", max_length=20) == "a\nb\nc"
    assert clean_multiline("a\tb", "note", max_length=20) == "a b"
    with pytest.raises(ValidationError) as long:
        clean_multiline("abc\ndef", "note", max_length=6)
    assert long.value.details == {"note": "note must be at most 6 characters long"}
    with pytest.raises(ValidationError) as control:
        clean_multiline("a\x00b", "note", max_length=6)
    assert control.value.details == {"note": "note must not contain control characters"}
    assert clean_multiline("abc\ndef", "note", max_length=7) == "abc\ndef"


@pytest.mark.parametrize("value", ["Muster\nAG", "a\rb", "x\ty", "nul\x00", "del\x7f"])
def test_single_line_text_rejects_control_characters(value: str) -> None:
    with pytest.raises(ValidationError) as error:
        clean_text(value, "street", max_length=70)
    assert error.value.details == {
        "street": "street must not contain line breaks or control characters"
    }


def test_address_is_normalised() -> None:
    address = Address(
        postal_code=" 8001 ",
        city=" Zürich ",
        country=CH,
        street=" Bahnhofstrasse ",
        house_number=" 1 ",
        supplement=" c/o Muster ",
    )
    assert address.street_line == "Bahnhofstrasse 1"
    assert address.lines() == ["c/o Muster", "Bahnhofstrasse 1", "8001 Zürich"]
    assert Address(postal_code="9490", city="Vaduz", country=CountryCode("LI")).lines() == [
        "9490 Vaduz",
    ]
    assert Address(postal_code="1", city="X", country=CH, house_number="5").street_line == "5"


@pytest.mark.parametrize(
    ("field", "kwargs", "message"),
    [
        ("postal_code", {"postal_code": " "}, "postal_code is required"),
        ("city", {"city": ""}, "city is required"),
        ("street", {"street": "x" * 71}, "street must be at most 70 characters long"),
        (
            "house_number",
            {"house_number": "1" * 17},
            "house_number must be at most 16 characters long",
        ),
        ("supplement", {"supplement": "x" * 71}, "supplement must be at most 70 characters long"),
        (
            "postal_code",
            {"postal_code": "1" * 17},
            "postal_code must be at most 16 characters long",
        ),
        ("city", {"city": "x" * 36}, "city must be at most 35 characters long"),
    ],
)
def test_address_validation(field: str, kwargs: dict[str, str], message: str) -> None:
    values: dict[str, object] = {"postal_code": "8001", "city": "Zürich", "country": CH, **kwargs}
    with pytest.raises(ValidationError) as error:
        Address(**values)  # type: ignore[arg-type]  # dynamic test values
    assert error.value.details == {field: message}
