import { z } from "zod";

export const MAX_RECIPIENTS = 5;

/** Split what was typed into the "to" field: commas, semicolons, spaces or new lines. */
export function parseRecipients(text: string): string[] {
  const found: string[] = [];
  for (const part of text.split(/[\s,;]+/)) {
    const address = part.trim();
    if (address !== "" && !found.some((known) => known.toLowerCase() === address.toLowerCase())) {
      found.push(address);
    }
  }
  return found;
}

export type RecipientProblem =
  | { readonly kind: "missing" }
  | { readonly kind: "tooMany" }
  | { readonly kind: "invalid"; readonly address: string };

/** What is wrong with the recipients, or null; the server checks again. */
export function recipientProblem(recipients: readonly string[]): RecipientProblem | null {
  if (recipients.length === 0) return { kind: "missing" };
  if (recipients.length > MAX_RECIPIENTS) return { kind: "tooMany" };
  const invalid = recipients.find((address) => !z.email().safeParse(address).success);
  return invalid === undefined ? null : { kind: "invalid", address: invalid };
}
