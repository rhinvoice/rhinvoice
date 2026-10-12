from uuid import UUID

import pytest

from rhinvoice.domain.country.profile import NOTICE_TREATMENTS
from rhinvoice.domain.country.registry import profile_of
from rhinvoice.domain.document.document import DocumentType
from rhinvoice.domain.shared.country import Country
from rhinvoice.domain.shared.errors import ValidationError
from rhinvoice.domain.shared.language import Language
from rhinvoice.domain.tax.treatment import TaxTreatment
from rhinvoice.domain.text.template import (
    MAX_NAME,
    MAX_TEMPLATE_TEXT,
    Placeholder,
    TextKind,
    TextTemplate,
    fill_placeholders,
    unknown_placeholders,
)
from tests.helpers import raises_exactly


def template(**overrides: object) -> TextTemplate:
    values: dict[str, object] = {
        "id": UUID(int=1),
        "kind": TextKind.PAYMENT,
        "document_type": DocumentType.INVOICE,
        "language": Language.DE,
        "name": "Fällig",
        "text": "Zahlbar bis {faellig}.",
    }
    values.update(overrides)
    return TextTemplate(**values)  # type: ignore[arg-type]  # test builder


def test_templates_are_cleaned() -> None:
    created = template(name="  Fällig ", text="  Zahlbar bis {faellig}.\r\nDanke.  ")
    assert created.name == "Fällig"
    assert created.text == "Zahlbar bis {faellig}.\nDanke."
    assert not created.is_default
    assert created.position == 0


def test_template_rules() -> None:
    with raises_exactly(ValidationError, "templates are for invoices and quotes") as wrong_type:
        template(document_type=DocumentType.CANCELLATION)
    assert wrong_type.value.field == "document_type"
    with raises_exactly(ValidationError, "name is required"):
        template(name=" ")
    with raises_exactly(ValidationError, f"name must be at most {MAX_NAME} characters long"):
        template(name="x" * (MAX_NAME + 1))
    with raises_exactly(ValidationError, "text is required") as empty:
        template(text=" \n ")
    assert empty.value.field == "text"
    with raises_exactly(
        ValidationError, f"text must be at most {MAX_TEMPLATE_TEXT} characters long"
    ):
        template(text="x" * (MAX_TEMPLATE_TEXT + 1))
    assert template(name="x" * MAX_NAME, text="x" * MAX_TEMPLATE_TEXT).text == "x" * 2000
    with pytest.raises(ValidationError) as unknown:
        template(text="Bis {faelig} und {due} und {faelig}")
    assert unknown.value.field == "text"
    assert unknown.value.code == "unknown_placeholder"
    assert str(unknown.value) == (
        "unknown placeholder {faelig}; available are "
        "{nummer}, {datum}, {faellig}, {kunde}, {betrag}, {waehrung}, {firma}"
    )
    assert template(document_type=DocumentType.QUOTE, text="{ } {a b} {}").text == "{ } {a b} {}"


def test_unknown_placeholders() -> None:
    assert unknown_placeholders("{nummer} {x} {kunde} {y} {x}") == ["x", "y"]
    assert unknown_placeholders("{{nummer}} {} {a b} {ä}") == []


def test_fill_placeholders() -> None:
    values = {Placeholder.NUMBER: "R20260001", Placeholder.DUE_DATE: "14.02.2026"}
    text = "Nr. {nummer}, fällig {faellig}, {kunde}, {unbekannt}, {nummer}"
    assert fill_placeholders(text, values) == (
        "Nr. R20260001, fällig 14.02.2026, {kunde}, {unbekannt}, R20260001"
    )
    assert fill_placeholders("{faellig}", {}) == "{faellig}"
    assert [placeholder.value for placeholder in Placeholder] == [
        "nummer",
        "datum",
        "faellig",
        "kunde",
        "betrag",
        "waehrung",
        "firma",
    ]


@pytest.mark.parametrize(
    ("treatment", "country", "language", "expected"),
    [
        (TaxTreatment.DOMESTIC, Country.CH, Language.DE, ""),
        (
            TaxTreatment.REVERSE_CHARGE,
            Country.CH,
            Language.DE,
            (
                "Übergang der Steuerschuld auf den Leistungsempfänger "
                "(Steuerschuldnerschaft des Leistungsempfängers, Reverse Charge)."
            ),
        ),
        (
            TaxTreatment.REVERSE_CHARGE,
            Country.LI,
            Language.DE,
            (
                "Übergang der Steuerschuld auf den Leistungsempfänger "
                "(Steuerschuldnerschaft des Leistungsempfängers, Reverse Charge)."
            ),
        ),
        (
            TaxTreatment.REVERSE_CHARGE,
            Country.DE,
            Language.DE,
            "Steuerschuldnerschaft des Leistungsempfängers.",
        ),
        (
            TaxTreatment.REVERSE_CHARGE,
            Country.AT,
            Language.DE,
            "Übergang der Steuerschuld auf den Leistungsempfänger (Reverse Charge).",
        ),
        (
            TaxTreatment.EXPORT,
            Country.LI,
            Language.DE,
            "Ort der Leistung im Ausland, nicht der MWST unterstellt.",
        ),
        (TaxTreatment.EXPORT, Country.DE, Language.DE, "Nicht im Inland steuerbare Leistung."),
        (
            TaxTreatment.SMALL_BUSINESS,
            Country.DE,
            Language.DE,
            "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet (Kleinunternehmerregelung).",
        ),
        (
            TaxTreatment.SMALL_BUSINESS,
            Country.AT,
            Language.DE,
            "Umsatzsteuerfrei aufgrund der Kleinunternehmerregelung (§ 6 Abs. 1 Z 27 UStG).",
        ),
        (TaxTreatment.SMALL_BUSINESS, Country.CH, Language.DE, "Nicht mehrwertsteuerpflichtig."),
        (TaxTreatment.EXEMPT, Country.CH, Language.DE, "Von der Mehrwertsteuer befreite Leistung."),
        (TaxTreatment.EXEMPT, Country.AT, Language.DE, "Steuerfreie Leistung."),
        (
            TaxTreatment.REVERSE_CHARGE,
            Country.DE,
            Language.EN,
            "Reverse charge: the recipient is liable for the VAT.",
        ),
        (TaxTreatment.DOMESTIC, Country.DE, Language.EN, ""),
        (
            TaxTreatment.INTRA_COMMUNITY,
            Country.DE,
            Language.DE,
            (
                "Steuerfreie innergemeinschaftliche Lieferung"
                " (§ 4 Nr. 1 Buchst. b i. V. m. § 6a UStG)."
            ),
        ),
        (
            TaxTreatment.GOODS_EXPORT,
            Country.LI,
            Language.DE,
            "Steuerbefreite Ausfuhrlieferung (Art. 23 Abs. 2 Ziff. 1 MWSTG).",
        ),
        (
            TaxTreatment.GOODS_EXPORT,
            Country.AT,
            Language.EN,
            "VAT exempt export delivery.",
        ),
        # Swiss companies export their goods; there is no intra-Community supply.
        (TaxTreatment.INTRA_COMMUNITY, Country.CH, Language.DE, ""),
    ],
)
def test_default_notices(
    treatment: TaxTreatment, country: Country, language: Language, expected: str
) -> None:
    assert profile_of(country).notice(treatment, language) == expected


def test_every_notice_treatment_has_a_text_everywhere() -> None:
    for country in Country:
        for treatment in profile_of(country).notice_treatments:
            for language in Language:
                assert profile_of(country).notice(treatment, language)
    assert profile_of(Country.DE).notice_treatments == NOTICE_TREATMENTS
    assert TaxTreatment.INTRA_COMMUNITY not in profile_of(Country.LI).notice_treatments
