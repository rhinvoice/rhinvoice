import { describe, expect, it } from "vitest";

import {
  defaultChoice,
  exportLanguage,
  exportUrl,
  fallbackName,
  periodOf,
  periodProblem,
  yearOptions,
  type ExportChoice,
} from "@/features/documents/export-model";

const CHOICE = defaultChoice("2026-10-29");

function choose(update: Partial<ExportChoice>): ExportChoice {
  return { ...CHOICE, ...update };
}

describe("defaultChoice", () => {
  it("is the previous full month as Excel without PDFs", () => {
    expect(CHOICE).toEqual({
      kind: "month",
      year: 2026,
      month: 9,
      quarter: 3,
      from: "2026-09-01",
      to: "2026-09-30",
      format: "xlsx",
      withPdfs: false,
    });
  });

  it("is December of the year before in January", () => {
    expect(defaultChoice("2027-01-15")).toMatchObject({
      year: 2026,
      month: 12,
      quarter: 4,
      from: "2026-12-01",
      to: "2026-12-31",
    });
  });

  it("knows the length of February", () => {
    expect(defaultChoice("2024-03-01")).toMatchObject({ to: "2024-02-29", quarter: 1 });
    expect(defaultChoice("2026-03-31")).toMatchObject({ to: "2026-02-28" });
  });
});

describe("periodOf", () => {
  it("is the month, quarter or year", () => {
    expect(periodOf(CHOICE)).toEqual({ start: "2026-09-01", end: "2026-09-30" });
    expect(periodOf(choose({ kind: "quarter", quarter: 1 }))).toEqual({
      start: "2026-01-01",
      end: "2026-03-31",
    });
    expect(periodOf(choose({ kind: "quarter", quarter: 4 }))).toEqual({
      start: "2026-10-01",
      end: "2026-12-31",
    });
    expect(periodOf(choose({ kind: "year", year: 2025 }))).toEqual({
      start: "2025-01-01",
      end: "2025-12-31",
    });
  });

  it("is the free days when they are valid", () => {
    const free = choose({ kind: "custom", from: "2026-01-15", to: "2026-02-14" });
    expect(periodOf(free)).toEqual({ start: "2026-01-15", end: "2026-02-14" });
    expect(periodOf(choose({ kind: "custom", from: "" }))).toBeNull();
  });
});

describe("periodProblem", () => {
  it("has nothing to say about months, quarters and years", () => {
    expect(periodProblem(CHOICE)).toBeNull();
    expect(periodProblem(choose({ kind: "year", from: "" }))).toBeNull();
  });

  it("asks for both days", () => {
    expect(periodProblem(choose({ kind: "custom", from: "", to: "2026-01-01" }))).toBe("missing");
    expect(periodProblem(choose({ kind: "custom", from: "2026-01-01", to: "" }))).toBe("missing");
  });

  it("refuses a period that ends before it starts", () => {
    const reversed = choose({ kind: "custom", from: "2026-02-01", to: "2026-01-31" });
    expect(periodProblem(reversed)).toBe("reversed");
    expect(periodProblem(choose({ kind: "custom", from: "2026-02-01", to: "2026-02-01" }))).toBe(
      null,
    );
  });

  it("allows at most ten years, as the server", () => {
    const longest = choose({ kind: "custom", from: "2016-01-01", to: "2025-12-31" });
    expect(periodProblem(longest)).toBeNull();
    expect(periodProblem({ ...longest, to: "2026-01-01" })).toBe("tooLong");
    const leap = choose({ kind: "custom", from: "2024-02-29", to: "2034-02-27" });
    expect(periodProblem(leap)).toBeNull();
    expect(periodProblem({ ...leap, to: "2034-02-28" })).toBe("tooLong");
    const plain = choose({ kind: "custom", from: "1990-02-28", to: "2000-02-27" });
    expect(periodProblem(plain)).toBeNull();
    expect(periodProblem({ ...plain, to: "2000-02-28" })).toBe("tooLong");
  });
});

describe("yearOptions", () => {
  it("joins the years with documents, the current and the chosen one, newest first", () => {
    expect(yearOptions("2026-10-29", [2024, 2026, 2015], 2025)).toEqual([2026, 2025, 2024, 2015]);
    expect(yearOptions("2026-01-02", [], 2025)).toEqual([2026, 2025]);
  });
});

describe("exportLanguage", () => {
  it("follows the language of the program", () => {
    expect(exportLanguage("de-CH")).toBe("de");
    expect(exportLanguage("de-DE")).toBe("de");
    expect(exportLanguage("de-AT")).toBe("de");
    expect(exportLanguage("fr-CH")).toBe("fr");
    expect(exportLanguage("it-CH")).toBe("it");
    expect(exportLanguage("en")).toBe("en");
  });
});

describe("exportUrl", () => {
  it("names the period, format, PDFs and language", () => {
    const period = { start: "2026-09-01", end: "2026-09-30" };
    expect(exportUrl(CHOICE, period, "fr-CH")).toBe(
      "/api/exports/invoices?start=2026-09-01&end=2026-09-30&format=xlsx&pdfs=false&language=fr",
    );
    expect(exportUrl(choose({ format: "csv", withPdfs: true }), period, "de-CH")).toBe(
      "/api/exports/invoices?start=2026-09-01&end=2026-09-30&format=csv&pdfs=true&language=de",
    );
  });
});

describe("fallbackName", () => {
  it("is a list, or a ZIP with the PDFs", () => {
    const period = { start: "2026-09-01", end: "2026-09-30" };
    expect(fallbackName(CHOICE, period)).toBe("export 2026-09-01 2026-09-30.xlsx");
    expect(fallbackName(choose({ format: "pdf", withPdfs: true }), period)).toBe(
      "export 2026-09-01 2026-09-30.zip",
    );
  });
});
