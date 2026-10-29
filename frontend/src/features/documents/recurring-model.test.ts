import { describe, expect, it } from "vitest";

import type { DocumentDetail } from "@/features/documents/api";
import { formToDraft } from "@/features/documents/document-form-model";
import type { Plan } from "@/features/documents/recurring-api";
import {
  documentToPlanForm,
  emptySettings,
  planSettings,
  planState,
  planToForm,
  settingsProblems,
  toPlanRequest,
} from "@/features/documents/recurring-model";
import type { Company } from "@/features/shared/company-api";
import { SWISS_PROFILE } from "@/test/country-profiles";

const COMPANY: Company = {
  id: "c",
  name: "Muster GmbH",
  address: {
    street: "Bahnhofstrasse",
    house_number: "1",
    supplement: "",
    postal_code: "8001",
    city: "Zürich",
    country: "CH",
  },
  country: "CH",
  default_currency: "CHF",
  default_language: "de",
  email: null,
  phone: "",
  website: "",
  vat_number: null,
  tax_number: "",
  commercial_register: "",
  small_business: false,
  cash_rounding: true,
  payment_terms_days: 30,
  accent_hue: 250,
  profile: SWISS_PROFILE,
};

const HOSTING = {
  kind: "item",
  description: "Hosting",
  details: "",
  quantity: "1",
  unit: "MON",
  unit_price: "29",
  discount_percent: "0",
  tax_category: "standard",
  supply: "service",
  article_id: null,
} as const;

const PLAN: Plan = {
  id: "p",
  name: "Hosting",
  customer_id: "k",
  customer_name: "Beispiel AG",
  customer_archived: false,
  interval: "quarterly",
  start_date: "2026-11-01",
  next_date: "2026-11-01",
  end_date: null,
  action: "send",
  service_period: false,
  active: true,
  finished: false,
  period_end: "2027-01-31",
  total: "31.35",
  template: {
    currency: "EUR",
    language: null,
    price_mode: "gross",
    lines: [HOSTING],
    discount_kind: "amount",
    discount_value: "5",
    subject: "Hosting",
    reference: "K-1",
    intro_text: "Hallo",
    payment_text: "Zahlbar",
    closing_text: "Danke",
    bank_account_id: "b1",
  },
  runs: [],
};

describe("recurring plans", () => {
  it("starts a new plan today, issuing every month", () => {
    expect(emptySettings("2026-10-12")).toEqual({
      name: "",
      interval: "monthly",
      startDate: "2026-10-12",
      endDate: "",
      action: "issue",
      servicePeriod: true,
    });
  });

  it("checks the plan's own settings", () => {
    expect(settingsProblems({ ...emptySettings("2026-10-12"), name: "Hosting" }).size).toBe(0);
    expect(Object.fromEntries(settingsProblems({ ...emptySettings(""), name: " " }))).toEqual({
      name: "required",
      startDate: "required",
    });
    expect(
      Object.fromEntries(
        settingsProblems({ ...emptySettings("2026-10-12"), name: "x", endDate: "2026-10-01" }),
      ),
    ).toEqual({ endDate: "endBeforeStart" });
    expect(
      settingsProblems({ ...emptySettings("2026-10-12"), name: "x", endDate: "2026-10-12" }).size,
    ).toBe(0);
  });

  it("edits a stored plan in the document form", () => {
    expect(planSettings({ ...PLAN, end_date: "2027-12-31" })).toEqual({
      name: "Hosting",
      interval: "quarterly",
      startDate: "2026-11-01",
      endDate: "2027-12-31",
      action: "send",
      servicePeriod: false,
    });
    expect(planSettings(PLAN).endDate).toBe("");
    const form = planToForm(PLAN, COMPANY, "de-CH");
    expect(form).toMatchObject({
      customer_id: "k",
      currency: "EUR",
      language: "de",
      price_mode: "gross",
      subject: "Hosting",
      reference: "K-1",
      intro_text: "Hallo",
      payment_text: "Zahlbar",
      closing_text: "Danke",
      discount_kind: "amount",
      discount_value: "5",
      issue_date: "",
      treatment: "",
      bank_account_id: "b1",
    });
    expect(form.lines.map((line) => [line.description, line.unit_price])).toEqual([
      ["Hosting", "29.00"],
    ]);
    const withoutDiscount = planToForm(
      { ...PLAN, template: { ...PLAN.template, language: "en", discount_value: null } },
      COMPANY,
      "de-CH",
    );
    expect([withoutDiscount.language, withoutDiscount.discount_value]).toEqual(["en", ""]);
    const ownDefault = { ...PLAN, template: { ...PLAN.template, bank_account_id: null } };
    expect(planToForm(ownDefault, COMPANY, "de-CH").bank_account_id).toBe("");
    const zero = { ...PLAN, template: { ...PLAN.template, discount_value: "0" } };
    expect(planToForm(zero, COMPANY, "de-CH").discount_value).toBe("");
  });

  it("builds the request from the settings and the form", () => {
    const settings = { ...planSettings(PLAN), name: " Hosting ", endDate: "2027-12-31" };
    const request = toPlanRequest(
      settings,
      formToDraft(planToForm(PLAN, COMPANY, "de-CH"), "de-CH"),
    );
    expect(request).toEqual({
      name: "Hosting",
      customer_id: "k",
      interval: "quarterly",
      start_date: "2026-11-01",
      end_date: "2027-12-31",
      action: "send",
      service_period: false,
      template: {
        currency: "EUR",
        language: "de",
        price_mode: "gross",
        lines: [
          {
            kind: "item",
            description: "Hosting",
            details: "",
            quantity: "1",
            unit: "MON",
            unit_price: "29.00",
            discount_percent: "0",
            tax_category: "standard",
            supply: "service",
            article_id: null,
          },
        ],
        discount_kind: "amount",
        discount_value: "5",
        subject: "Hosting",
        reference: "K-1",
        intro_text: "Hallo",
        payment_text: "Zahlbar",
        closing_text: "Danke",
        bank_account_id: "b1",
      },
    });
    expect(
      toPlanRequest(planSettings(PLAN), formToDraft(planToForm(PLAN, COMPANY, "de-CH"), "de-CH"))
        .end_date,
    ).toBeNull();
  });

  it("repeats an invoice without its dates and tax choice", () => {
    const invoice = {
      customer_id: "k",
      currency: "CHF",
      language: "de",
      price_mode: "net",
      issue_date: "2026-10-01",
      due_date: "2026-10-31",
      service_from: "2026-10-01",
      service_to: "2026-10-31",
      subject: "Wartung",
      reference: "",
      intro_text: "",
      payment_text: "",
      closing_text: "",
      discount_kind: "percent",
      discount_value: "0",
      treatment: "export",
      treatment_overridden: true,
      lines: [{ ...HOSTING, id: "l1", tax_rate: "8.1", amount: "29.00" }],
    } as unknown as DocumentDetail;
    const form = documentToPlanForm(invoice, "de-CH");
    expect(form).toMatchObject({
      subject: "Wartung",
      issue_date: "",
      due_date: "",
      service_from: "",
      service_to: "",
      treatment: "",
      override_reason: "",
    });
    expect(form.lines[0]?.key).not.toBe("l1");
  });

  it("fills in what a draft request may leave out", () => {
    const request = toPlanRequest(planSettings(PLAN), {
      customer_id: "k",
      price_mode: "net",
      discount_kind: "percent",
      subject: "",
      reference: "",
      intro_text: "",
      payment_text: "",
      closing_text: "",
      override_reason: "",
    });
    expect(request.template).toMatchObject({
      currency: "CHF",
      language: null,
      lines: [],
      discount_value: null,
      bank_account_id: null,
    });
  });

  it("says how a plan stands", () => {
    const run = {
      period_start: "2026-11-01",
      at: "2026-11-01T09:00:00Z",
      outcome: "issued",
      document_id: "d",
      code: "",
      message: "",
    } as const;
    const now = new Date("2026-11-01T09:10:00Z");
    expect(planState(PLAN, now)).toBe("active");
    expect(planState({ ...PLAN, runs: [run] }, now)).toBe("active");
    expect(planState({ ...PLAN, runs: [{ ...run, code: "mail_auth_failed" }] }, now)).toBe(
      "problem",
    );
    // Being written for 10 minutes: still running; after 15 minutes: interrupted.
    const interrupted = { ...run, code: "interrupted" };
    expect(planState({ ...PLAN, runs: [interrupted] }, now)).toBe("active");
    expect(planState({ ...PLAN, runs: [interrupted] }, new Date("2026-11-01T09:15:00Z"))).toBe(
      "problem",
    );
    expect(planState({ ...PLAN, active: false }, now)).toBe("paused");
    expect(planState({ ...PLAN, active: false, finished: true }, now)).toBe("finished");
  });
});
