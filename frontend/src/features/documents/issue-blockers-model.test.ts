import { describe, expect, it } from "vitest";

import { blockerFixes, knownBlockers } from "@/features/documents/issue-blockers-model";

describe("issue blockers", () => {
  it("keeps the codes the editor can fix, in order", () => {
    expect(knownBlockers(["bank_account_missing", "unheard_of", "company_tax_id_missing"])).toEqual(
      ["bank_account_missing", "company_tax_id_missing"],
    );
    expect(knownBlockers(["toString"])).toEqual([]);
  });

  it("offers each fix once, in the order it is first needed", () => {
    expect(
      blockerFixes([
        "reverse_charge_needs_vat_number",
        "company_tax_id_missing",
        "company_vat_id_missing",
        "customer_vat_id_missing",
      ]),
    ).toEqual(["customer", "company"]);
    expect(blockerFixes(["bank_account_missing", "company_vat_number_missing"])).toEqual([
      "bank_account",
      "company",
    ]);
    expect(blockerFixes([])).toEqual([]);
  });
});
