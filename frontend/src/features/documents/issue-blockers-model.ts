/** What fills in a missing detail without leaving the editor. */
export type BlockerFix = "bank_account" | "company" | "customer";

const FIXES = {
  bank_account_missing: "bank_account",
  reverse_charge_needs_vat_number: "customer",
  company_vat_number_missing: "company",
  company_tax_id_missing: "company",
  customer_vat_number_required: "customer",
  company_vat_id_missing: "company",
  customer_vat_id_missing: "customer",
} as const satisfies Record<string, BlockerFix>;

export type BlockerCode = keyof typeof FIXES;

/** The codes the editor can explain and fix; others only show when issuing. */
export function knownBlockers(codes: readonly string[]): BlockerCode[] {
  return codes.filter((code): code is BlockerCode => Object.hasOwn(FIXES, code));
}

/** One fix per kind, in the order of the first detail that needs it. */
export function blockerFixes(codes: readonly BlockerCode[]): BlockerFix[] {
  return [...new Set(codes.map((code) => FIXES[code]))];
}
