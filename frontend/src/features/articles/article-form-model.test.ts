import { describe, expect, it } from "vitest";

import {
  articleFieldFor,
  articleSchema,
  articleToForm,
  emptyArticle,
  formToRequest,
  priceCurrencies,
} from "@/features/articles/article-form-model";
import { translatorFor } from "@/lib/i18n";

const schema = articleSchema(translatorFor("de-DE"), "de-DE");

describe("article form", () => {
  it("validates name and prices", () => {
    expect(schema.safeParse(emptyArticle()).success).toBe(false);
    const ok = { ...emptyArticle(), name: "Beratung", price_chf: "1.234,5", price_eur: "" };
    expect(schema.safeParse(ok).success).toBe(true);
    expect(schema.safeParse({ ...ok, price_chf: "1,00001" }).success).toBe(false);
    expect(schema.safeParse({ ...ok, price_chf: "-5" }).success).toBe(false);
  });

  it("builds requests with canonical prices", () => {
    const request = formToRequest(
      { ...emptyArticle(), name: "Beratung", price_chf: "1.234,5", price_eur: "" },
      "de-DE",
    );
    expect(request.prices).toEqual({ CHF: "1234.5" });
    expect(
      formToRequest({ ...emptyArticle(), name: "X", price_eur: "10" }, "de-DE").prices,
    ).toEqual({ EUR: "10" });
  });

  it("formats prices for editing", () => {
    const form = articleToForm(
      {
        id: "1",
        number: "1",
        name: "Beratung",
        description: "",
        group: "",
        unit: "HUR",
        unit_label_de: "Std.",
        unit_label_en: "h",
        tax_category: "standard",
        supply: "goods",
        prices: { CHF: "150.00" },
        archived: false,
        created_at: "2026-01-01T00:00:00Z",
      },
      "de-DE",
    );
    expect(form.price_chf).toBe("150,00");
    expect(form.supply).toBe("goods");
    expect(form.price_eur).toBe("");
  });

  it("maps API error fields", () => {
    expect(articleFieldFor("prices.CHF")).toBe("price_chf");
    expect(articleFieldFor("prices.EUR")).toBe("price_eur");
    expect(articleFieldFor("name")).toBe("name");
    expect(articleFieldFor("x")).toBeNull();
  });
});

describe("priceCurrencies", () => {
  it("puts the company's currency first", () => {
    expect(priceCurrencies("EUR")).toEqual(["EUR", "CHF"]);
    expect(priceCurrencies("CHF")).toEqual(["CHF", "EUR"]);
    // Before the company is loaded or set up.
    expect(priceCurrencies(undefined)).toEqual(["CHF", "EUR"]);
  });
});
