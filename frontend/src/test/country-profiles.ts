import type { CountryProfile } from "@/features/shared/country-profile-model";

/** Profiles as the API sends them (GET /api/reference/country-profiles). */
export const SWISS_PROFILE: CountryProfile = {
  country: "CH",
  vat_system: "swiss",
  vat_area: ["CH", "LI"],
  rates: { standard: "8.1", reduced: "2.6", special: "3.8" },
  terms: {
    de: {
      tax_name: "MWST",
      vat_number_label: "MWST-Nr.",
      vat_number_field: "UID / MWST-Nummer",
      vat_number_hint:
        "Pflicht auf Rechnungen, wenn die Firma MWST-pflichtig ist, z. B. CHE-123.456.789 MWST.",
      small_business: "Nicht MWST-pflichtig (Umsatz unter CHF 100'000)",
      special_rate: "Sondersatz Beherbergung",
    },
    en: {
      tax_name: "VAT",
      vat_number_label: "VAT no.",
      vat_number_field: "UID / VAT number",
      vat_number_hint:
        "Required on invoices of VAT registered companies, e.g. CHE-123.456.789 MWST.",
      small_business: "Not VAT registered (turnover below CHF 100,000)",
      special_rate: "Accommodation rate",
    },
  },
  number_style: "apostrophe",
  payment_codes: ["epc_to_eea", "swiss_qr_bill"],
  default_currency: "CHF",
  cash_rounding: true,
  tax_number: false,
};

export const GERMAN_PROFILE: CountryProfile = {
  country: "DE",
  vat_system: "eu",
  vat_area: ["DE"],
  rates: { standard: "19", reduced: "7", special: null },
  terms: {
    de: {
      tax_name: "USt.",
      vat_number_label: "USt-IdNr.",
      vat_number_field: "USt-IdNr.",
      vat_number_hint: "Oder die Steuernummer: eine der beiden muss auf der Rechnung stehen.",
      small_business: "Kleinunternehmer nach § 19 UStG",
      special_rate: null,
    },
    en: {
      tax_name: "VAT",
      vat_number_label: "VAT no.",
      vat_number_field: "VAT ID",
      vat_number_hint: "Or the tax number: one of both must be on the invoice.",
      small_business: "Small business (§ 19 UStG)",
      special_rate: null,
    },
  },
  number_style: "dot_comma",
  payment_codes: ["epc"],
  default_currency: "EUR",
  cash_rounding: false,
  tax_number: true,
};
