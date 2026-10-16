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
      bad_debts: "Debitorenverluste",
      write_off_hint:
        "Bei Abrechnung nach vereinbartem Entgelt ist der Betrag eine Entgeltsminderung (Art. 41 MWSTG).",
      special_rate: "Sondersatz Beherbergung",
    },
    en: {
      tax_name: "VAT",
      vat_number_label: "VAT no.",
      vat_number_field: "UID / VAT number",
      vat_number_hint:
        "Required on invoices of VAT registered companies, e.g. CHE-123.456.789 MWST.",
      small_business: "Not VAT registered (turnover below CHF 100,000)",
      bad_debts: "Bad debts",
      write_off_hint:
        "By agreed consideration the amount reduces the consideration (Art. 41 MWSTG).",
      special_rate: "Accommodation rate",
    },
    fr: {
      tax_name: "TVA",
      vat_number_label: "N° TVA",
      vat_number_field: "IDE / numéro TVA",
      vat_number_hint:
        "Obligatoire sur les factures des entreprises assujetties à la TVA, p. ex. CHE-123.456.789 TVA.",
      small_business: "Non assujetti à la TVA (chiffre d’affaires inférieur à 100 000 francs)",
      bad_debts: "Pertes sur débiteurs",
      write_off_hint: "Le montant diminue la contre-prestation (art. 41 LTVA).",
      special_rate: "Taux spécial pour l’hébergement",
    },
    it: {
      tax_name: "IVA",
      vat_number_label: "N. IVA",
      vat_number_field: "IDI / numero IVA",
      vat_number_hint:
        "Obbligatorio sulle fatture delle imprese assoggettate all’IVA, p. es. CHE-123.456.789 IVA.",
      small_business: "Non assoggettato all’IVA (cifra d’affari inferiore a 100 000 franchi)",
      bad_debts: "Perdite su debitori",
      write_off_hint: "L’importo riduce la controprestazione (art. 41 LIVA).",
      special_rate: "Aliquota speciale per il settore alberghiero",
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
      bad_debts: "Forderungsausfälle",
      write_off_hint:
        "Bei Soll-Versteuerung berichtigen Sie die Umsatzsteuer (§ 17 Abs. 2 Nr. 1 UStG).",
      special_rate: null,
    },
    en: {
      tax_name: "VAT",
      vat_number_label: "VAT no.",
      vat_number_field: "VAT ID",
      vat_number_hint: "Or the tax number: one of both must be on the invoice.",
      small_business: "Small business (§ 19 UStG)",
      bad_debts: "Bad debts",
      write_off_hint:
        "Correct the VAT in the period it became uncollectible (§ 17 Abs. 2 Nr. 1 UStG).",
      special_rate: null,
    },
    fr: {
      tax_name: "TVA",
      vat_number_label: "N° TVA",
      vat_number_field: "N° d’identification TVA",
      vat_number_hint: "Ou le numéro fiscal : l’un des deux doit figurer sur la facture.",
      small_business: "Petite entreprise (§ 19 UStG)",
      bad_debts: "Créances irrécouvrables",
      write_off_hint: "Corrigez la TVA dans la période concernée (§ 17 Abs. 2 Nr. 1 UStG).",
      special_rate: null,
    },
    it: {
      tax_name: "IVA",
      vat_number_label: "N. IVA",
      vat_number_field: "N. di identificazione IVA",
      vat_number_hint: "Oppure il numero fiscale: uno dei due deve figurare sulla fattura.",
      small_business: "Piccola impresa (§ 19 UStG)",
      bad_debts: "Crediti inesigibili",
      write_off_hint: "Correggete l’IVA nel periodo interessato (§ 17 Abs. 2 Nr. 1 UStG).",
      special_rate: null,
    },
  },
  number_style: "dot_comma",
  payment_codes: ["epc"],
  default_currency: "EUR",
  cash_rounding: false,
  tax_number: true,
};
