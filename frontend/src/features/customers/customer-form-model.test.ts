import { describe, expect, it } from "vitest";

import type { Customer } from "@/features/customers/api";
import {
  customerFieldFor,
  customerSchema,
  customerToForm,
  emptyCustomer,
  EU_COUNTRIES,
  exemptInsteadOfReverseCharge,
  formToRequest,
} from "@/features/customers/customer-form-model";
import { translatorFor } from "@/lib/i18n";

const t = translatorFor("de-CH");
const schema = customerSchema(t, "de-CH");

function issues(values: Record<string, unknown>): Record<string, string> {
  const result = schema.safeParse({ ...emptyCustomer("CH"), ...values });
  if (result.success) return {};
  return Object.fromEntries(
    result.error.issues.map((issue) => [issue.path.join("."), issue.message]),
  );
}

describe("customer form", () => {
  it("requires the name that matches the kind and a postal address", () => {
    expect(issues({})).toEqual({
      company_name: "Bitte ausfüllen.",
      postal_code: "Bitte ausfüllen.",
      city: "Bitte ausfüllen.",
    });
    expect(issues({ kind: "person", postal_code: "3000", city: "Bern" })).toEqual({
      last_name: "Bitte ausfüllen.",
    });
    expect(issues({ company_name: "X", postal_code: "1", city: "Y", has_delivery: true })).toEqual({
      delivery_postal_code: "Bitte ausfüllen.",
      delivery_city: "Bitte ausfüllen.",
    });
  });

  it("validates e-mail, UID, discount and payment terms", () => {
    const base = { company_name: "X", postal_code: "1", city: "Y" };
    expect(issues({ ...base, email: "nope" })["email"]).toContain("gültige E-Mail");
    expect(issues({ ...base, vat_number: "CHE-123.456.789" })["vat_number"]).toBe(
      "Die Prüfziffer der UID stimmt nicht – bitte prüfen.",
    );
    expect(issues({ ...base, default_discount: "150" })["default_discount"]).toBe(
      "Bitte eine Zahl von 0 bis 100 eingeben.",
    );
    expect(issues({ ...base, default_discount: "2.555" })["default_discount"]).toBe(
      "Höchstens 2 Nachkommastellen.",
    );
    expect(issues({ ...base, payment_terms_days: "400" })["payment_terms_days"]).toBe(
      "Bitte eine ganze Zahl von 0 bis 365 eingeben.",
    );
    expect(
      issues({ ...base, default_discount: "2,5", payment_terms_days: "30", email: "a@b.example" }),
    ).toEqual({});
  });

  it("builds the API request", () => {
    const request = formToRequest(
      {
        ...emptyCustomer("CH"),
        company_name: "Muster AG",
        contact_person: "Frau X",
        postal_code: "8001",
        city: "Zürich",
        default_discount: "2,5",
        payment_terms_days: "10",
        default_currency: "EUR",
        email: "",
      },
      "de-DE",
    );
    expect(request.default_discount).toBe("2.5");
    expect(request.payment_terms_days).toBe(10);
    expect(request.default_currency).toBe("EUR");
    expect(request.default_language).toBeNull();
    expect(request.email).toBeNull();
    expect(request.delivery_address).toBeNull();
    expect(request.contact_person).toBe("Frau X");
    const person = formToRequest(
      {
        ...emptyCustomer("DE"),
        kind: "person",
        company_name: "left over",
        contact_person: "x",
        last_name: "Muster",
        has_delivery: true,
        delivery_city: "Vaduz",
        delivery_postal_code: "9490",
        delivery_country: "LI",
      },
      "de-CH",
    );
    expect(person.company_name).toBe("");
    expect(person.contact_person).toBe("");
    expect(person.default_discount).toBe("0");
    expect(person.payment_terms_days).toBeNull();
    expect(person.delivery_address).toMatchObject({ city: "Vaduz", country: "LI" });
  });

  it("round-trips a customer from the API", () => {
    const customer: Customer = {
      id: "1",
      number: "1001",
      kind: "company",
      display_name: "Muster AG",
      company_name: "Muster AG",
      salutation: "",
      first_name: "",
      last_name: "",
      contact_person: "",
      address: {
        street: "A",
        house_number: "1",
        supplement: "",
        postal_code: "8001",
        city: "Zürich",
        country: "CH",
      },
      delivery_address: null,
      email: null,
      phone: "",
      vat_number: null,
      buyer_reference: "",
      group: "",
      default_currency: null,
      default_language: "en",
      tax_exempt: false,
      default_discount: "2.5",
      payment_terms_days: 20,
      note: "",
      archived: false,
      created_at: "2026-01-01T00:00:00Z",
    };
    const form = customerToForm(customer, "de-DE");
    expect(form.default_discount).toBe("2,5");
    expect(form.payment_terms_days).toBe("20");
    expect(form.default_language).toBe("en");
    expect(form.has_delivery).toBe(false);
    expect(formToRequest(form, "de-DE").default_discount).toBe("2.5");
    expect(
      customerToForm({ ...customer, default_discount: "0", payment_terms_days: null }, "de-CH"),
    ).toMatchObject({
      default_discount: "",
      payment_terms_days: "",
    });
  });

  it("round-trips delivery address, contact data and defaults", () => {
    const form = customerToForm(
      {
        id: "2",
        number: "1002",
        kind: "person",
        display_name: "Anna Muster",
        company_name: "",
        salutation: "Frau",
        first_name: "Anna",
        last_name: "Muster",
        contact_person: "",
        address: {
          street: "B",
          house_number: "2",
          supplement: "",
          postal_code: "3000",
          city: "Bern",
          country: "CH",
        },
        delivery_address: {
          street: "C",
          house_number: "3",
          supplement: "Lager",
          postal_code: "9490",
          city: "Vaduz",
          country: "LI",
        },
        email: "anna@example.com",
        phone: "+41 31 000 00 00",
        vat_number: "CHE-123.456.788",
        buyer_reference: "04011000-1234512345-06",
        group: "VIP",
        default_currency: "EUR",
        default_language: null,
        tax_exempt: true,
        default_discount: "0",
        payment_terms_days: null,
        note: "",
        archived: false,
        created_at: "2026-01-01T00:00:00Z",
      },
      "de-CH",
    );
    expect(form).toMatchObject({
      has_delivery: true,
      delivery_supplement: "Lager",
      delivery_country: "LI",
      email: "anna@example.com",
      vat_number: "CHE-123.456.788",
      default_currency: "EUR",
      default_language: "",
    });
    expect(issues({ ...form })).toEqual({});
    const request = formToRequest(form, "de-CH");
    expect(request.delivery_address).toMatchObject({ supplement: "Lager", country: "LI" });
    expect(request.vat_number).toBe("CHE-123.456.788");
    expect(request.email).toBe("anna@example.com");
    // Kept although the field is only shown for German customers.
    expect(form.buyer_reference).toBe("04011000-1234512345-06");
    expect(request.buyer_reference).toBe("04011000-1234512345-06");
  });

  it("limits the buyer reference to 100 characters", () => {
    const base = { company_name: "X", postal_code: "1", city: "Y" };
    expect(issues({ ...base, buyer_reference: "1".repeat(101) })["buyer_reference"]).toBeDefined();
    expect(issues({ ...base, buyer_reference: "991-33333TEST-33" })).toEqual({});
  });

  it("maps API error fields to form fields", () => {
    expect(customerFieldFor("address.city")).toBe("city");
    expect(customerFieldFor("delivery_address.city")).toBe("delivery_city");
    expect(customerFieldFor("vat_number")).toBe("vat_number");
    expect(customerFieldFor("unknown")).toBeNull();
  });
});

describe("exemptInsteadOfReverseCharge", () => {
  const austrian = { kind: "company", country: "AT", vat_number: "ATU12345678", tax_exempt: true };

  it("warns about an EU business with VAT number marked exempt", () => {
    expect(exemptInsteadOfReverseCharge(austrian)).toBe(true);
    expect(EU_COUNTRIES.size).toBe(27);
  });

  it("does not warn otherwise", () => {
    expect(exemptInsteadOfReverseCharge({ ...austrian, tax_exempt: false })).toBe(false);
    expect(exemptInsteadOfReverseCharge({ ...austrian, kind: "person" })).toBe(false);
    expect(exemptInsteadOfReverseCharge({ ...austrian, vat_number: " " })).toBe(false);
    expect(exemptInsteadOfReverseCharge({ ...austrian, country: "CH" })).toBe(false);
  });
});
