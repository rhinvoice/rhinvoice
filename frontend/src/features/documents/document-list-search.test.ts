import { describe, expect, it } from "vitest";

import {
  documentAriaSort,
  DOCUMENT_LIST_DEFAULTS,
  isPayable,
  parseDocumentListSearch,
  toggleDocumentSort,
  viewCount,
  viewFilter,
} from "@/features/documents/document-list-search";

const CUSTOMER = "0b5f6d3e-2c4a-4f7e-9a1b-3c5d7e9f1a2b";

describe("parseDocumentListSearch", () => {
  it("applies defaults", () => {
    expect(parseDocumentListSearch({}, "invoice")).toEqual(DOCUMENT_LIST_DEFAULTS);
  });

  it("reads valid values and rejects others", () => {
    expect(
      parseDocumentListSearch(
        { q: "x".repeat(120), view: "overdue", sort: "total", dir: "asc", page: 3 },
        "invoice",
      ),
    ).toEqual({
      ...DOCUMENT_LIST_DEFAULTS,
      q: "x".repeat(100),
      view: "overdue",
      sort: "total",
      dir: "asc",
      page: 3,
    });
    expect(parseDocumentListSearch({ view: "overdue", sort: "x", page: 1.5 }, "quote")).toEqual(
      DOCUMENT_LIST_DEFAULTS,
    );
    expect(parseDocumentListSearch({ view: "expired", q: 5 }, "quote").view).toBe("expired");
  });

  it("reads the year and the customer", () => {
    const read = (raw: Record<string, unknown>) => parseDocumentListSearch(raw, "invoice");
    expect(read({ year: 2025, customer: CUSTOMER.toUpperCase() })).toMatchObject({
      year: 2025,
      customer: CUSTOMER,
    });
    expect(read({ year: "2024" }).year).toBe(2024);
    for (const year of [1899, 10_000, 2025.5, "abc", null]) {
      expect(read({ year }).year).toBe("all");
    }
    expect(read({ year: 1900 }).year).toBe(1900);
    expect(read({ year: 9999 }).year).toBe(9999);
    for (const customer of ["x", 42, `${CUSTOMER}0`, ` ${CUSTOMER}`]) {
      expect(read({ customer }).customer).toBe("");
    }
  });
});

describe("viewFilter", () => {
  it.each([
    ["invoice", "all", ["invoice", "cancellation"], []],
    ["invoice", "open", ["invoice"], ["issued", "partially_paid", "overdue"]],
    ["invoice", "paid", ["invoice"], ["paid"]],
    ["quote", "all", ["quote"], []],
    ["quote", "expired", ["quote"], ["expired"]],
  ] as const)("%s %s", (kind, view, types, statuses) => {
    expect(viewFilter(kind, view)).toEqual({ types, statuses });
  });
});

describe("sorting", () => {
  const current = { ...DOCUMENT_LIST_DEFAULTS, page: 4 };

  it("flips the direction of the current column", () => {
    expect(toggleDocumentSort(current, "created_at")).toEqual({
      sort: "created_at",
      dir: "asc",
      page: 1,
    });
    expect(toggleDocumentSort({ ...current, dir: "asc" }, "created_at").dir).toBe("desc");
  });

  it("starts text columns ascending and the others descending", () => {
    expect(toggleDocumentSort(current, "customer").dir).toBe("asc");
    expect(toggleDocumentSort(current, "number").dir).toBe("asc");
    expect(toggleDocumentSort(current, "total").dir).toBe("desc");
  });

  it("reports aria-sort", () => {
    expect(documentAriaSort(current, "created_at")).toBe("descending");
    expect(documentAriaSort({ ...current, dir: "asc" }, "created_at")).toBe("ascending");
    expect(documentAriaSort(current, "total")).toBe("none");
  });
});

describe("viewCount", () => {
  const counts = [
    { status: "draft", count: 2 },
    { status: "issued", count: 3 },
    { status: "partially_paid", count: 1 },
    { status: "overdue", count: 4 },
    { status: "paid", count: 5 },
  ] as const;

  it("adds up the statuses of a view", () => {
    expect(viewCount("invoice", "all", counts)).toBeUndefined();
    expect(viewCount("invoice", "open", counts)).toBe(8);
    expect(viewCount("invoice", "overdue", counts)).toBe(4);
    expect(viewCount("invoice", "cancelled", counts)).toBe(0);
    expect(viewCount("quote", "draft", counts)).toBe(2);
  });
});

describe("isPayable", () => {
  it.each([
    ["invoice", "issued", true],
    ["invoice", "partially_paid", true],
    ["invoice", "overdue", true],
    ["invoice", "paid", false],
    ["invoice", "draft", false],
    ["invoice", "cancelled", false],
    ["cancellation", "issued", false],
    ["quote", "sent", false],
  ] as const)("%s %s", (type, status, payable) => {
    expect(isPayable({ type, display_status: status })).toBe(payable);
  });
});
