import { describe, expect, it } from "vitest";

import type { DocumentDetail } from "@/features/documents/api";
import { conversionRequest, hasOptions, initialChoice } from "@/features/documents/convert-model";
import { DOCUMENT } from "@/test/documents";

const [item, text] = DOCUMENT.lines as [
  DocumentDetail["lines"][number],
  DocumentDetail["lines"][number],
];
const QUOTE: DocumentDetail = {
  ...DOCUMENT,
  type: "quote",
  status: "sent",
  issue_date: "2026-01-05",
  due_date: "2026-02-04",
  lines: [
    text,
    item,
    { ...item, id: "large", description: "Paket L", in_total: "alternative", alternative_to: "l1" },
    { ...item, id: "extra", description: "Mehrsprachigkeit", in_total: "optional" },
  ],
};

describe("turning a quote into an invoice", () => {
  it("asks only when the quote has items outside its total", () => {
    expect(hasOptions(QUOTE.lines)).toBe(true);
    expect(hasOptions(DOCUMENT.lines)).toBe(false);
  });

  it("ticks the items in the total", () => {
    expect(initialChoice(QUOTE.lines)).toEqual(["l1"]);
  });

  it("previews the invoice of the chosen items as ordinary lines, dated today", () => {
    const request = conversionRequest(QUOTE, new Set(["large", "extra"]), "de-CH", "2026-03-01");
    expect(request).toMatchObject({
      type: "invoice",
      customer_id: "k",
      issue_date: "2026-03-01",
      due_date: null,
    });
    expect(
      request.lines?.map((line) => [line.description, line.in_total, line.alternative_to]),
    ).toEqual([
      ["Phase 2", "yes", null],
      ["Paket L", "yes", null],
      ["Mehrsprachigkeit", "yes", null],
    ]);
  });
});
