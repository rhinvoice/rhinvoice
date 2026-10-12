import { describe, expect, it } from "vitest";

import {
  bankAccountSchema,
  bankAccountToForm,
  emptyBankAccount,
  formToRequest as bankRequest,
} from "@/features/company/bank-account-form-model";
import {
  companyFieldFor,
  companySchema,
  companyToForm,
  emptyCompany,
  formToRequest,
} from "@/features/company/company-form-model";
import { translatorFor } from "@/lib/i18n";
import { GERMAN_PROFILE } from "@/test/country-profiles";

const t = translatorFor("de-CH");

describe("company form", () => {
  it("defaults depend on the country", () => {
    expect(emptyCompany("CH", "CHF")).toMatchObject({
      country: "CH",
      default_currency: "CHF",
      cash_rounding: false,
    });
    expect(emptyCompany("DE", "EUR")).toMatchObject({ default_currency: "EUR" });
  });

  it("validates and builds the request", () => {
    const schema = companySchema(t, "de-CH");
    expect(schema.safeParse(emptyCompany("CH", "CHF")).success).toBe(false);
    const values = {
      ...emptyCompany("LI", "CHF"),
      name: "Muster Anstalt",
      postal_code: "9490",
      city: "Vaduz",
    };
    expect(schema.safeParse(values).success).toBe(true);
    expect(schema.safeParse({ ...values, payment_terms_days: "400" }).success).toBe(false);
    const request = formToRequest(values);
    expect(request.address.country).toBe("LI");
    expect(request.email).toBeNull();
    expect(request.payment_terms_days).toBe(30);
    expect(companyFieldFor("address.postal_code")).toBe("postal_code");
    expect(companyFieldFor("vat_number")).toBe("vat_number");
    expect(companyFieldFor("nope")).toBeNull();
  });
});

describe("company round trip", () => {
  it("fills the form from the API", () => {
    const form = companyToForm({
      id: "1",
      name: "Muster GmbH",
      address: {
        street: "Hauptstrasse",
        house_number: "1",
        supplement: "",
        postal_code: "1010",
        city: "Wien",
        country: "AT",
      },
      country: "AT",
      default_currency: "EUR",
      default_language: "de",
      email: null,
      phone: "",
      website: "",
      vat_number: null,
      tax_number: "",
      commercial_register: "",
      small_business: true,
      cash_rounding: false,
      payment_terms_days: 14,
      accent_hue: 120,
      // The profile does not matter here; any country's will do.
      profile: GERMAN_PROFILE,
    });
    expect(form).toMatchObject({
      country: "AT",
      email: "",
      vat_number: "",
      payment_terms_days: "14",
      small_business: true,
      accent_hue: 120,
    });
    expect(formToRequest(form)).toMatchObject({ email: null, payment_terms_days: 14 });
    expect(
      formToRequest({ ...form, email: "info@muster.example", vat_number: "ATU13585627" }),
    ).toMatchObject({ email: "info@muster.example", vat_number: "ATU13585627" });
  });
});

describe("bank account form", () => {
  const schema = bankAccountSchema(t, "de-CH");
  const valid = {
    ...emptyBankAccount("CHF", "Muster"),
    bank_name: "Bank",
    iban: "CH93 0076 2011 6238 5295 7",
  };

  function messages(values: Record<string, unknown>): Record<string, string> {
    const result = schema.safeParse({ ...valid, ...values });
    return result.success
      ? {}
      : Object.fromEntries(result.error.issues.map((i) => [i.path.join("."), i.message]));
  }

  it("accepts a regular account with QR-IBAN and BIC", () => {
    expect(messages({ qr_iban: "CH44 3199 9123 0008 8901 2", bic: "ubswchzh80a" })).toEqual({});
  });

  it("explains IBAN problems", () => {
    expect(messages({ iban: "" })["iban"]).toBeDefined();
    expect(messages({ iban: "CH930076201162385295" })["iban"]).toBe(
      "Eine IBAN aus CH hat 21 Zeichen – bitte prüfen.",
    );
    expect(messages({ iban: "CH9300762011623852958" })["iban"]).toBe(
      "Die Prüfziffern stimmen nicht – bitte auf Tippfehler prüfen.",
    );
    expect(messages({ iban: "CH4431999123000889012" })["iban"]).toContain("QR-IBAN");
    expect(messages({ qr_iban: "CH9300762011623852957" })["qr_iban"]).toContain("30000 und 31999");
    expect(messages({ qr_iban: "CH44" })["qr_iban"]).toBeDefined();
    // A wrong length of a QR-IBAN is reported as a typo, like a wrong check digit.
    expect(messages({ qr_iban: "CH44 3199 9123 0008 8901 23" })["qr_iban"]).toBe(
      "Die Prüfziffern stimmen nicht – bitte auf Tippfehler prüfen.",
    );
    expect(messages({ bic: "XX" })["bic"]).toBe(
      "Ein BIC hat 8 oder 11 Zeichen, z. B. UBSWCHZH80A.",
    );
  });

  it("normalises the request and round-trips", () => {
    const request = bankRequest({
      ...valid,
      qr_iban: "ch44 3199 9123 0008 8901 2",
      bic: "ubsw chzh 80a",
    });
    expect(request.iban).toBe("CH9300762011623852957");
    expect(request.qr_iban).toBe("CH4431999123000889012");
    expect(request.bic).toBe("UBSWCHZH80A");
    expect(bankRequest(valid)).toMatchObject({ qr_iban: null, bic: null });
    const form = bankAccountToForm({
      id: "1",
      currency: "EUR",
      bank_name: "B",
      holder: "H",
      iban: "LI21088100002324013AA",
      iban_formatted: "LI21 0881 0000 2324 013A A",
      qr_iban: null,
      bic: null,
      is_default: true,
    });
    expect(form).toMatchObject({ qr_iban: "", bic: "", iban: "LI21 0881 0000 2324 013A A" });
  });
});
