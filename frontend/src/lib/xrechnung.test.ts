import { describe, expect, it } from "vitest";

import { asksForBuyerReference, referenceHint, xrechnungOnly } from "@/lib/xrechnung";

const german = { address: { country: "DE" }, buyer_reference: "" };

describe("xrechnung", () => {
  it("asks German customers only", () => {
    expect(asksForBuyerReference("DE")).toBe(true);
    for (const country of ["CH", "LI", "AT", "FR"]) {
      expect(asksForBuyerReference(country)).toBe(false);
    }
  });

  it("names the customer's Leitweg-ID below the reference", () => {
    expect(referenceHint({ ...german, buyer_reference: " 991-33333TEST-33 " })).toEqual({
      key: "documents.referenceHintFixed",
      value: "991-33333TEST-33",
    });
  });

  it("asks German customers without one for a reference", () => {
    expect(referenceHint(german)).toEqual({ key: "documents.referenceHintXRechnung", value: "" });
    expect(referenceHint({ ...german, buyer_reference: " " }).key).toBe(
      "documents.referenceHintXRechnung",
    );
  });

  it("keeps the usual hint elsewhere and before a customer is chosen", () => {
    const austrian = { address: { country: "AT" }, buyer_reference: "kept from before" };
    expect(referenceHint(austrian)).toEqual({ key: "documents.referenceHint", value: "" });
    expect(referenceHint(undefined).key).toBe("documents.referenceHint");
  });

  it("lists only what is not listed already", () => {
    expect(
      xrechnungOnly(["buyer_vat_id_missing", "buyer_reference_missing"], ["buyer_vat_id_missing"]),
    ).toEqual(["buyer_reference_missing"]);
    expect(xrechnungOnly([], ["buyer_vat_id_missing"])).toEqual([]);
  });
});
