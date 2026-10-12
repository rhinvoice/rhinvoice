import pytest
from hypothesis import given
from hypothesis import strategies as st

from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.iban import Bic, Iban
from rhinvoice.domain.tax.vat_number import VatNumber
from tests.helpers import raises_exactly

# Official examples: SIX (CH, QR-IBAN), SWIFT IBAN registry (DE, AT, LI).
CH_IBAN = "CH9300762011623852957"
CH_QR_IBAN = "CH4431999123000889012"
DE_IBAN = "DE89370400440532013000"
AT_IBAN = "AT611904300234573201"
LI_IBAN = "LI21088100002324013AA"


@pytest.mark.parametrize("value", [CH_IBAN, CH_QR_IBAN, DE_IBAN, AT_IBAN, LI_IBAN])
def test_valid_ibans(value: str) -> None:
    assert Iban(value).value == value


def test_parse_normalises_paper_format() -> None:
    iban = Iban.parse(" ch93 0076 2011 6238 5295 7 ")
    assert iban.value == CH_IBAN
    assert iban.country == "CH"
    assert iban.formatted() == "CH93 0076 2011 6238 5295 7"
    assert str(iban) == CH_IBAN


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("9300762011623852957", "IBAN must start with a country code and two digits"),
        ("CHXX00762011623852957", "IBAN must start with a country code and two digits"),
        ("CH93-0076", "IBAN must start with a country code and two digits"),
        ("ZZ9300762011623852957", "IBANs from ZZ are not supported"),
        ("CH930076201162385295", "an IBAN from CH has 21 characters, got 20"),
        ("CH9300762011623852958", "IBAN check digits are wrong, please check for typos"),
    ],
)
def test_invalid_ibans(value: str, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        Iban(value)
    assert error.value.details == {"iban": message}


def test_qr_iban_detection() -> None:
    assert Iban(CH_QR_IBAN).is_qr_iban
    assert not Iban(CH_IBAN).is_qr_iban
    assert not Iban(DE_IBAN).is_qr_iban
    assert not Iban(LI_IBAN).is_qr_iban


def _with_check_digits(country: str, bban: str) -> str:
    numeric = "".join(str(int(char, 36)) for char in bban + country + "00")
    return f"{country}{98 - int(numeric) % 97:02d}{bban}"


@pytest.mark.parametrize(
    ("iid", "expected"), [("29999", False), ("30000", True), ("31999", True), ("32000", False)]
)
def test_qr_iid_range_boundaries(iid: str, expected: bool) -> None:
    assert Iban(_with_check_digits("CH", f"{iid}123456789012")).is_qr_iban is expected


@given(st.text(alphabet="0123456789", min_size=17, max_size=17))
def test_generated_swiss_ibans_validate_and_detect_typos(bban: str) -> None:
    iban = _with_check_digits("CH", bban)
    assert Iban(iban).value == iban
    wrong_digit = str((int(iban[10]) + 1) % 10)
    with pytest.raises(ValidationError):
        Iban(iban[:10] + wrong_digit + iban[11:])


def test_bic() -> None:
    assert Bic.parse(" ubsw ch zh 80a ").value == "UBSWCHZH80A"
    assert str(Bic("POFICHBEXXX")) == "POFICHBEXXX"
    assert Bic("COBADEFF").value == "COBADEFF"
    for invalid in ["UBSWCHZH8", "1BSWCHZH80A", "UBSW"]:
        with raises_exactly(
            ValidationError,
            "BIC must have 8 or 11 characters, e.g. UBSWCHZH80A",
        ) as error:
            Bic(invalid)
        assert error.value.field == "bic"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CHE-123.456.788", "CHE-123.456.788"),
        ("che123456788", "CHE-123.456.788"),
        ("CHE 123 456 788 mwst", "CHE-123.456.788 MWST"),
        ("CHE-123.456.788 TVA", "CHE-123.456.788 TVA"),
        ("CHE-000.000.000", "CHE-000.000.000"),  # check digit 11 maps to 0
        ("de 123 456 789", "DE123456789"),
        ("ATU12345678", "ATU12345678"),
        ("FR40303265045", "FR40303265045"),
        ("nl 123456789 b01", "NL123456789B01"),
        ("  12345  ", "12345"),
        ("GB 123 4567 89", "GB 123 4567 89"),
    ],
)
def test_vat_number_parsing(raw: str, expected: str) -> None:
    assert str(VatNumber.parse(raw)) == expected


def test_vat_number_length_limit() -> None:
    assert len(VatNumber.parse("X" * 40).value) == 40


def test_vat_number_prefix() -> None:
    assert VatNumber.parse("DE123456789").country_prefix == "DE"


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("   ", "VAT number is empty"),
        ("X" * 41, "VAT number must be at most 40 characters"),
        ("CHE-123.456.789", "the check digit of the Swiss UID is wrong"),
        ("CHE-123.456.78", "a Swiss UID has the form CHE-123.456.789"),
        ("CHE-123.456.788 VAT", "a Swiss UID has the form CHE-123.456.789"),
        ("DE12345678", "a German VAT number has the form DE123456789"),
        ("ATU1234567", "an Austrian VAT number has the form ATU12345678"),
        ("AT12345678", "an Austrian VAT number has the form ATU12345678"),
    ],
)
def test_invalid_vat_numbers(raw: str, message: str) -> None:
    with pytest.raises(ValidationError) as error:
        VatNumber.parse(raw)
    assert error.value.details == {"vat_number": message}


def test_swiss_uid_check_digit_ten_is_never_valid() -> None:
    # Base numbers whose check digit would be 10 are never assigned (BFS UID spec).
    weights = (5, 4, 3, 2, 7, 6, 5, 4)
    candidates = [
        f"{n:08d}"
        for n in range(1, 2000)
        if 11 - sum(int(d) * w for d, w in zip(f"{n:08d}", weights, strict=True)) % 11 == 10
    ]
    digits = candidates[0]
    for last in range(10):
        number = digits + str(last)
        with pytest.raises(ValidationError):
            VatNumber.parse(f"CHE-{number[:3]}.{number[3:6]}.{number[6:]}")
