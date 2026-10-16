/**
 * The XRechnung is the e-invoice of German authorities. It needs a buyer reference
 * (BT-10): the customer's Leitweg-ID or fixed buyer reference if set, else the
 * reference of the invoice. Customers elsewhere need no XRechnung.
 */

/** Only German customers are asked for a Leitweg-ID and warned about the XRechnung. */
export function asksForBuyerReference(country: string): boolean {
  return country === "DE";
}

export interface BuyerReferenceSource {
  readonly address: { readonly country: string };
  readonly buyer_reference: string;
}

export interface ReferenceHint {
  readonly key:
    "documents.referenceHint" | "documents.referenceHintXRechnung" | "documents.referenceHintFixed";
  readonly value: string;
}

/** The hint below the reference field of an invoice, for its customer (if chosen). */
export function referenceHint(customer: BuyerReferenceSource | undefined): ReferenceHint {
  if (customer === undefined || !asksForBuyerReference(customer.address.country)) {
    return { key: "documents.referenceHint", value: "" };
  }
  const fixed = customer.buyer_reference.trim();
  return fixed === ""
    ? { key: "documents.referenceHintXRechnung", value: "" }
    : { key: "documents.referenceHintFixed", value: fixed };
}

/** What the XRechnung lacks beyond what is already listed for the e-invoice in the PDF. */
export function xrechnungOnly<P extends string>(
  xrechnung: readonly P[],
  listed: readonly P[],
): P[] {
  return xrechnung.filter((problem) => !listed.includes(problem));
}
