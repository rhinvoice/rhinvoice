import type { FieldErrors } from "react-hook-form";
import { describe, expect, it } from "vitest";

import type { ArticleOption, CustomerOption, DocumentDetail } from "@/features/documents/api";
import {
  customerDefaults,
  documentFieldFor,
  documentSchema,
  documentSummaryItems,
  documentToForm,
  emptyDocument,
  emptyLine,
  fieldId,
  customerVatHint,
  formToDraft,
  lineRates,
  ownTreatment,
  goodsHintKey,
  hasSupply,
  lineFromArticle,
  MAX_LINES,
  type DocumentFormValues,
} from "@/features/documents/document-form-model";
import type { Company } from "@/features/shared/company-api";
import { translatorFor } from "@/lib/i18n";
import { SWISS_PROFILE } from "@/test/country-profiles";

const t = translatorFor("de-CH");
const schema = documentSchema(t, "de-CH");

const ADDRESS = {
  street: "Bahnhofstrasse",
  house_number: "1",
  supplement: "",
  postal_code: "8001",
  city: "Zürich",
  country: "CH",
} as const;

const COMPANY: Company = {
  id: "c",
  name: "Muster GmbH",
  address: ADDRESS,
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

const CUSTOMER: CustomerOption = {
  id: "k",
  number: "1001",
  kind: "company",
  display_name: "Beispiel AG",
  company_name: "Beispiel AG",
  salutation: "",
  first_name: "",
  last_name: "",
  contact_person: "",
  address: ADDRESS,
  delivery_address: null,
  email: null,
  phone: "",
  vat_number: null,
  group: "",
  default_currency: null,
  default_language: null,
  tax_exempt: false,
  default_discount: "0",
  payment_terms_days: null,
  note: "",
  archived: false,
  created_at: "2026-01-01T00:00:00Z",
};

function valid(overrides: Partial<DocumentFormValues> = {}): DocumentFormValues {
  return {
    ...emptyDocument(COMPANY),
    customer_id: "k",
    lines: [{ ...emptyLine(), key: "a", description: "Beratung", unit_price: "150" }],
    ...overrides,
  };
}

function issues(values: DocumentFormValues): Record<string, string> {
  const result = schema.safeParse(values);
  if (result.success) return {};
  return Object.fromEntries(
    result.error.issues.map((issue) => [issue.path.join("."), issue.message]),
  );
}

describe("document form", () => {
  it("starts with the company defaults and one empty line", () => {
    const empty = emptyDocument({ ...COMPANY, default_currency: "EUR", default_language: "en" });
    expect(empty).toMatchObject({ currency: "EUR", language: "en", customer_id: "" });
    expect(empty.lines).toHaveLength(1);
    expect(emptyLine()).toMatchObject({ kind: "item", quantity: "1", unit: "C62" });
    expect(emptyLine("text")).toMatchObject({ kind: "text", quantity: "", unit: "" });
    expect(emptyLine().key).not.toBe(emptyLine().key);
  });

  it("accepts a valid draft", () => {
    expect(issues(valid())).toEqual({});
  });

  it("requires a customer and descriptions", () => {
    const text = { ...emptyLine("text"), key: "t" };
    const item = { ...emptyLine(), key: "i", quantity: "" };
    expect(issues(valid({ customer_id: "", lines: [text, item] }))).toEqual({
      customer_id: "Bitte wählen Sie einen Kunden.",
      "lines.0.description": "Bitte ausfüllen.",
      "lines.1.description": "Bitte ausfüllen.",
      "lines.1.quantity": "Bitte ausfüllen.",
    });
  });

  it("allows negative quantities but not negative prices", () => {
    const line = { ...emptyLine(), key: "x", description: "Gutschrift" };
    expect(issues(valid({ lines: [{ ...line, quantity: "-2", unit_price: "10" }] }))).toEqual({});
    expect(issues(valid({ lines: [{ ...line, unit_price: "-10" }] }))).toEqual({
      "lines.0.unit_price": "Bitte geben Sie eine Zahl ein, z. B. 150.00.",
    });
    expect(issues(valid({ lines: [{ ...line, quantity: "1.23456" }] }))).toEqual({
      "lines.0.quantity": "Höchstens 4 Nachkommastellen.",
    });
  });

  it("checks discount, dates and the reason of a manual tax treatment", () => {
    expect(issues(valid({ discount_value: "120" }))).toEqual({
      discount_value: "Bitte einen Wert zwischen 0 und 100 eingeben.",
    });
    expect(issues(valid({ discount_kind: "amount", discount_value: "120" }))).toEqual({});
    expect(issues(valid({ discount_value: "12,5" }))).toEqual({});
    expect(issues(valid({ issue_date: "2026-02-01", due_date: "2026-01-31" }))).toEqual({
      due_date: "Das Fälligkeitsdatum liegt vor dem Datum.",
    });
    expect(issues(valid({ issue_date: "2026-02-01", due_date: "2026-02-01" }))).toEqual({});
    expect(issues(valid({ service_from: "2026-02-01", service_to: "2026-01-01" }))).toEqual({
      service_to: "Der Leistungszeitraum endet vor seinem Beginn.",
    });
    expect(issues(valid({ service_from: "2026-01-01", service_to: "2026-01-01" }))).toEqual({});
    expect(issues(valid({ treatment: "export" }))).toEqual({
      override_reason: "Bitte begründen Sie die manuelle Wahl.",
    });
    expect(issues(valid({ treatment: "export", override_reason: "Ausfuhr" }))).toEqual({});
  });

  it("limits the number of lines", () => {
    const lines = Array.from({ length: MAX_LINES + 1 }, (_, index) => ({
      ...emptyLine("text"),
      key: String(index),
      description: "x",
    }));
    expect(issues(valid({ lines }))).toEqual({
      lines: "Ein Dokument hat höchstens 500 Positionen.",
    });
  });
});

describe("customer and article defaults", () => {
  it("takes currency, language and discount from the customer", () => {
    expect(customerDefaults(CUSTOMER, COMPANY, "de-CH")).toEqual({
      customer_id: "k",
      currency: "CHF",
      language: "de",
      discount_value: "",
    });
    expect(
      customerDefaults(
        { ...CUSTOMER, default_currency: "EUR", default_language: "en", default_discount: "2.50" },
        COMPANY,
        "de-DE",
      ),
    ).toEqual({ customer_id: "k", currency: "EUR", language: "en", discount_value: "2,5" });
  });

  it("fills a line from an article in the document currency", () => {
    const article: ArticleOption = {
      id: "a1",
      number: "A-1",
      name: "Wartung",
      description: "pro Stunde",
      group: "",
      unit: "HUR",
      unit_label_de: "Std.",
      unit_label_en: "h",
      tax_category: "reduced",
      supply: "goods",
      prices: { CHF: "120.00" },
      archived: false,
      created_at: "2026-01-01T00:00:00Z",
    };
    const line = { ...emptyLine("text"), key: "x", unit_price: "5" };
    expect(lineFromArticle(line, article, "CHF", "de-CH")).toEqual({
      ...line,
      kind: "item",
      description: "Wartung",
      details: "pro Stunde",
      unit: "HUR",
      unit_price: "120.00",
      tax_category: "reduced",
      supply: "goods",
      article_id: "a1",
    });
    // No EUR price: the typed price stays.
    expect(lineFromArticle(line, article, "EUR", "de-CH").unit_price).toBe("5");
  });
});

const DETAIL: DocumentDetail = {
  id: "d",
  type: "invoice",
  status: "draft",
  display_status: "draft",
  number: null,
  customer_id: "k",
  recipient: null,
  currency: "EUR",
  language: "de",
  price_mode: "gross",
  treatment: "export",
  treatment_overridden: true,
  goods_treatment: "goods_export",
  discount_kind: "amount",
  discount_value: "50",
  issue_date: "2026-01-05",
  due_date: null,
  service_from: null,
  service_to: "2026-01-31",
  subject: "Website",
  reference: "PO-1",
  intro_text: "Hallo",
  payment_text: "Sofort",
  closing_text: "Danke",
  notice: "",
  lines: [
    {
      id: "l1",
      kind: "item",
      description: "Beratung",
      details: "",
      quantity: "1.5",
      unit: "HUR",
      unit_price: "1234.5",
      discount_percent: "10",
      tax_category: "standard",
      supply: "goods",
      tax_rate: null,
      amount: "1666.58",
      article_id: "a1",
    },
    {
      id: "l2",
      kind: "text",
      description: "Phase 2",
      details: "Details",
      quantity: "1",
      unit: null,
      unit_price: "0",
      discount_percent: "0",
      tax_category: "standard",
      supply: "service",
      tax_rate: null,
      amount: null,
      article_id: null,
    },
  ],
  totals: {
    currency: "EUR",
    subtotal: "0.00",
    discount: "0.00",
    net: "0.00",
    tax: "0.00",
    gross: "0.00",
    rounding: "0.00",
    total: "0.00",
    groups: [],
  },
  payments: [],
  paid_amount: "0.00",
  open_amount: "0.00",
  write_off: null,
  written_off_amount: "0.00",
  events: [],
  source_id: null,
  cancelled_by_id: null,
  converted_to_id: null,
  created_at: "2026-01-05T08:00:00Z",
  issued_at: null,
  imported: false,
  has_pdf: false,
};

describe("conversion", () => {
  it("formats a stored draft for editing", () => {
    const form = documentToForm(DETAIL, "de-DE");
    expect(form).toMatchObject({
      currency: "EUR",
      price_mode: "gross",
      issue_date: "2026-01-05",
      due_date: "",
      service_to: "2026-01-31",
      discount_value: "50",
      treatment: "export",
      override_reason: "",
    });
    expect(form.lines).toEqual([
      {
        key: "l1",
        kind: "item",
        description: "Beratung",
        details: "",
        quantity: "1,5",
        unit: "HUR",
        unit_price: "1234,50",
        discount_percent: "10",
        tax_category: "standard",
        supply: "goods",
        article_id: "a1",
      },
      {
        key: "l2",
        kind: "text",
        description: "Phase 2",
        details: "Details",
        quantity: "",
        unit: "",
        unit_price: "",
        discount_percent: "",
        tax_category: "standard",
        supply: "service",
        article_id: null,
      },
    ]);
    const automatic = documentToForm(
      {
        ...DETAIL,
        treatment_overridden: false,
        discount_value: "0",
        issue_date: null,
        service_to: null,
      },
      "de-CH",
    );
    // A treatment of goods is never one chosen for the document.
    expect(documentToForm({ ...DETAIL, treatment: "intra_community" }, "de-DE").treatment).toBe("");
    expect(automatic).toMatchObject({
      treatment: "",
      discount_value: "",
      issue_date: "",
      service_to: "",
    });
  });

  it("names what to keep for goods leaving the country tax free", () => {
    const goods = [{ kind: "item" as const, supply: "goods" as const }];
    const services = [
      { kind: "item" as const, supply: "service" as const },
      { kind: "text" as const, supply: "goods" as const },
    ];
    expect(hasSupply(goods, "goods")).toBe(true);
    expect(hasSupply(services, "goods")).toBe(false);
    expect(hasSupply(services, "service")).toBe(true);
    expect(goodsHintKey("intra_community", goods)).toBe("documents.intraCommunityHint");
    expect(goodsHintKey("goods_export", goods)).toBe("documents.goodsExportHint");
    expect(goodsHintKey("domestic", goods)).toBeNull();
    expect(goodsHintKey(undefined, goods)).toBeNull();
    expect(goodsHintKey("goods_export", services)).toBeNull();
  });

  it("offers no VAT for goods with a tax free treatment of their own", () => {
    const rates = { standard: "8.1", reduced: "2.6" };
    expect(ownTreatment("goods", "goods_export")).toBe("goods_export");
    expect(ownTreatment("service", "goods_export")).toBeNull();
    expect(ownTreatment("goods", null)).toBeNull();
    expect(ownTreatment("goods", undefined)).toBeNull();
    expect(lineRates(rates, "goods_export")).toEqual({ standard: "0", reduced: "0" });
    expect(lineRates(rates, "domestic")).toBe(rates);
    expect(lineRates(rates, null)).toBe(rates);
    expect(lineRates(undefined, "intra_community")).toBeUndefined();
  });

  it("says what the customer's VAT number would change", () => {
    const goods = [{ kind: "item" as const, supply: "goods" as const }];
    const mixed = [...goods, { kind: "item" as const, supply: "service" as const }];
    expect(customerVatHint(mixed, "eu", "domestic", "domestic")).toEqual({
      withNumber: "reverse_charge",
      without: "domestic",
    });
    expect(customerVatHint([], "swiss", "export", null)).toEqual({
      withNumber: "reverse_charge",
      without: "export",
    });
    expect(customerVatHint(goods, "eu", "domestic", "domestic")).toEqual({
      withNumber: "intra_community",
      without: "domestic",
    });
    expect(customerVatHint(goods, "eu", "domestic", null)).toEqual({
      withNumber: "intra_community",
      without: "domestic",
    });
    // From Switzerland goods are exported either way.
    expect(customerVatHint(goods, "swiss", "export", "goods_export")).toBeNull();
  });

  it("builds the API request with canonical numbers", () => {
    const draft = formToDraft(
      { ...documentToForm(DETAIL, "de-DE"), override_reason: "Ausfuhr" },
      "de-DE",
    );
    expect(draft).toMatchObject({
      customer_id: "k",
      issue_date: "2026-01-05",
      due_date: null,
      service_from: null,
      discount_kind: "amount",
      discount_value: "50",
      treatment_override: "export",
      override_reason: "Ausfuhr",
    });
    expect(draft.lines).toEqual([
      {
        kind: "item",
        description: "Beratung",
        details: "",
        quantity: "1.5",
        unit: "HUR",
        unit_price: "1234.50",
        discount_percent: "10",
        tax_category: "standard",
        supply: "goods",
        article_id: "a1",
      },
      {
        kind: "text",
        description: "Phase 2",
        details: "Details",
        quantity: "1",
        unit: null,
        unit_price: "0",
        discount_percent: "0",
        tax_category: "standard",
        supply: "service",
        article_id: null,
      },
    ]);
    const plain = formToDraft(
      valid({
        lines: [{ ...emptyLine(), key: "z", description: "x", unit: "" }],
        override_reason: "ignored",
      }),
      "de-CH",
    );
    expect(plain).toMatchObject({
      discount_value: "0",
      treatment_override: null,
      override_reason: "",
    });
    expect(plain.lines?.[0]).toMatchObject({ unit: null, unit_price: "0", discount_percent: "0" });
  });
});

describe("errors", () => {
  it("maps API fields onto form fields", () => {
    expect(documentFieldFor("discount")).toBe("discount_value");
    expect(documentFieldFor("treatment_override")).toBe("treatment");
    expect(documentFieldFor("customer_id")).toBe("customer_id");
    expect(documentFieldFor("lines")).toBe("lines");
    expect(documentFieldFor("lines.3.quantity")).toBe("lines.3.quantity");
    expect(documentFieldFor("lines.3.unknown")).toBeNull();
    expect(documentFieldFor("lines.x.quantity")).toBeNull();
    expect(documentFieldFor("type")).toBeNull();
  });

  it("derives element ids from field paths", () => {
    expect(fieldId("lines.2.unit_price")).toBe("lines-2-unit_price");
    expect(fieldId("subject")).toBe("subject");
  });

  it("lists errors in visual order with line numbers", () => {
    const lineErrors = [] as unknown[];
    lineErrors[1] = {
      description: { type: "custom", message: "Bitte ausfüllen." },
      quantity: { type: "custom", message: "Zahl" },
    };
    const errors = {
      subject: { type: "custom", message: "Zu lang" },
      customer_id: { type: "custom", message: "Kunde fehlt" },
      lines: Object.assign(lineErrors, {
        message: "Zu viele",
        root: { type: "custom", message: "Mindestens eine Position" },
      }),
      closing_text: { type: "custom", message: "Zu lang" },
    } as unknown as FieldErrors<DocumentFormValues>;
    expect(documentSummaryItems(errors, t)).toEqual([
      { fieldId: "customer_id", message: "Kunde fehlt" },
      { fieldId: "subject", message: "Zu lang" },
      { fieldId: "lines", message: "Mindestens eine Position" },
      { fieldId: "lines-1-description", message: "Position 2: Bitte ausfüllen." },
      { fieldId: "lines-1-quantity", message: "Position 2: Zahl" },
      { fieldId: "closing_text", message: "Zu lang" },
    ]);
    expect(documentSummaryItems({}, t)).toEqual([]);
    expect(
      documentSummaryItems(
        {
          lines: { type: "server", message: "Mindestens eine Position" },
        },
        t,
      ),
    ).toEqual([{ fieldId: "lines", message: "Mindestens eine Position" }]);
  });
});
