"""What can be imported, and which column of a file probably holds which field.

Column names differ between programs and spreadsheets ("KdNr", "Kunden-Nr.",
"Customer number"); each field lists the usual names. The suggestion is only a
start: the person checks it and can save the mapping as a template.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rhinvoice.application.importing.parsing import normalize


class ImportTarget(StrEnum):
    CUSTOMERS = "customers"
    ARTICLES = "articles"


@dataclass(frozen=True, slots=True)
class ImportField:
    key: str
    synonyms: tuple[str, ...]
    """Usual column names; compared after ``normalize``."""
    required: bool = False


CUSTOMER_FIELDS: tuple[ImportField, ...] = (
    ImportField(
        "number",
        (
            "Kundennummer",
            "Kunden-Nr.",
            "KdNr",
            "Kd-Nr",
            "KundenNr",
            "Kunde Nr",
            "Nummer",
            "Nr",
            "Customer number",
            "Customer no",
            "Customer ID",
            "Number",
            "Debitor",
            "Debitorennummer",
        ),
    ),
    ImportField(
        "company_name",
        (
            "Firma",
            "Firmenname",
            "Firmenbezeichnung",
            "Unternehmen",
            "Name",
            "Name 1",
            "Name1",
            "Company",
            "Company name",
            "Organisation",
            "Organization",
        ),
    ),
    ImportField("salutation", ("Anrede", "Salutation", "Titel", "Title")),
    ImportField("first_name", ("Vorname", "First name", "Firstname", "Given name")),
    ImportField(
        "last_name",
        ("Nachname", "Familienname", "Name 2", "Name2", "Last name", "Lastname", "Surname"),
    ),
    ImportField(
        "contact_person",
        (
            "Kontaktperson",
            "Ansprechpartner",
            "Ansprechperson",
            "Kontakt",
            "z. Hd.",
            "zHd",
            "Contact",
            "Contact person",
        ),
    ),
    ImportField(
        "street",
        (
            "Strasse",
            "Straße",
            "Str",
            "Strasse und Hausnummer",
            "Strasse Nr",
            "Adresse",
            "Anschrift",
            "Street",
            "Address",
            "Address line 1",
        ),
    ),
    ImportField("house_number", ("Hausnummer", "Hausnr", "Haus-Nr.", "House number", "No")),
    ImportField(
        "supplement",
        ("Adresszusatz", "Zusatz", "Postfach", "Address line 2", "Supplement", "c/o"),
    ),
    ImportField(
        "postal_code", ("PLZ", "Postleitzahl", "Zip", "Zip code", "Postal code", "Postcode")
    ),
    ImportField("city", ("Ort", "Stadt", "Wohnort", "Gemeinde", "City", "Town")),
    ImportField("postal_city", ("PLZ Ort", "PLZ/Ort", "PLZ_Ort", "PLZ und Ort", "Zip city")),
    ImportField("country", ("Land", "Staat", "Ländercode", "Country", "Country code")),
    ImportField("email", ("E-Mail", "Email", "Mail", "E-Mail-Adresse", "Email address")),
    ImportField(
        "phone",
        (
            "Telefon",
            "Tel",
            "Tel.",
            "Telefonnummer",
            "Phone",
            "Phone number",
            "Mobil",
            "Natel",
            "Handy",
        ),
    ),
    ImportField(
        "vat_number",
        (
            "UID",
            "UID-Nr.",
            "UID Nummer",
            "USt-IdNr.",
            "UStIdNr",
            "USt-ID",
            "MWST-Nr.",
            "MWST Nr",
            "Umsatzsteuer-ID",
            "VAT",
            "VAT number",
            "VAT ID",
        ),
    ),
    ImportField("group", ("Gruppe", "Kundengruppe", "Kategorie", "Group", "Category")),
    ImportField("default_currency", ("Währung", "Waehrung", "Currency")),
    ImportField("default_language", ("Sprache", "Korrespondenzsprache", "Language")),
    ImportField("default_discount", ("Rabatt", "Kundenrabatt", "Rabatt %", "Discount")),
    ImportField(
        "payment_terms_days",
        ("Zahlungsziel", "Zahlungsfrist", "Zahlungsziel Tage", "Payment terms", "Days"),
    ),
    ImportField("tax_exempt", ("Steuerbefreit", "MWST-befreit", "Tax exempt")),
    ImportField(
        "note",
        (
            "Notiz",
            "Notizen",
            "Bemerkung",
            "Bemerkungen",
            "Kommentar",
            "Info",
            "Note",
            "Notes",
            "Remarks",
        ),
    ),
    ImportField(
        "customer_since",
        (
            "Kunde seit",
            "Kunden seit",
            "Angelegt",
            "Angelegt am",
            "Erstellt",
            "Erstellt am",
            "Erfasst",
            "Erfasst am",
            "Anlagedatum",
            "Erstelldatum",
            "Eintrittsdatum",
            "Customer since",
            "Created",
            "Created at",
            "Since",
        ),
    ),
)

ARTICLE_FIELDS: tuple[ImportField, ...] = (
    ImportField(
        "number",
        (
            "Artikelnummer",
            "Artikel-Nr.",
            "ArtNr",
            "Art.-Nr.",
            "Artikelnr",
            "Nummer",
            "Nr",
            "Article number",
            "Item number",
            "SKU",
            "Number",
        ),
    ),
    ImportField(
        "name",
        (
            "Bezeichnung",
            "Artikelbezeichnung",
            "Artikel",
            "Artikelname",
            "Name",
            "Kurztext",
            "Titel",
            "Article",
            "Item",
            "Title",
        ),
        required=True,
    ),
    ImportField(
        "description",
        ("Beschreibung", "Langtext", "Text", "Details", "Artikeltext", "Description"),
    ),
    ImportField("unit", ("Einheit", "Mengeneinheit", "ME", "Unit")),
    ImportField(
        "price",
        (
            "Preis",
            "Verkaufspreis",
            "VK",
            "VK-Preis",
            "Einzelpreis",
            "Netto",
            "Nettopreis",
            "Price",
            "Unit price",
            "Sales price",
        ),
    ),
    ImportField("price_chf", ("Preis CHF", "VK CHF", "CHF", "Price CHF")),
    ImportField("price_eur", ("Preis EUR", "VK EUR", "EUR", "Euro", "Price EUR")),
    ImportField(
        "tax_category",
        (
            "MWST",
            "MwSt",
            "MWST-Satz",
            "MwSt-Satz",
            "USt",
            "Steuersatz",
            "Steuer",
            "VAT",
            "VAT rate",
            "Tax",
        ),
    ),
    ImportField(
        "group",
        ("Gruppe", "Artikelgruppe", "Warengruppe", "Kategorie", "Group", "Category"),
    ),
    ImportField(
        "supply",
        ("Ware/Dienstleistung", "Leistungsart", "Artikelart", "Art", "Goods/service"),
    ),
)

FIELDS: dict[ImportTarget, tuple[ImportField, ...]] = {
    ImportTarget.CUSTOMERS: CUSTOMER_FIELDS,
    ImportTarget.ARTICLES: ARTICLE_FIELDS,
}


def field_keys(target: ImportTarget) -> frozenset[str]:
    return frozenset(field.key for field in FIELDS[target])


def suggest_mapping(headers: tuple[str, ...], target: ImportTarget) -> dict[str, int]:
    """Map fields to the columns whose names match their own or usual names.

    Each column is used at most once; when several fields could take a column, the
    first field in the list wins (e.g. "Name" becomes the company name).
    """
    names = [normalize(header) for header in headers]
    mapping: dict[str, int] = {}
    for field in FIELDS[target]:
        candidates = {normalize(field.key), *(normalize(name) for name in field.synonyms)}
        for index, name in enumerate(names):
            if name in candidates and index not in mapping.values():
                mapping[field.key] = index
                break
    return mapping
