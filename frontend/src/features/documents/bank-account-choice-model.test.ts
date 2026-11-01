import { describe, expect, it } from "vitest";

import {
  accountLabel,
  accountsFor,
  offersAccountChoice,
  shortIban,
  validAccountChoice,
} from "@/features/documents/bank-account-choice-model";
import { translatorFor } from "@/lib/i18n";

const t = translatorFor("de-CH");

const own = {
  id: "own",
  currency: "EUR" as const,
  bank_name: "Musterbank",
  holder: "Muster GmbH",
  iban_formatted: "DE89 3704 0044 0532 0130 00",
  is_default: true,
  third_party: false,
};
const provider = {
  ...own,
  id: "provider",
  bank_name: "Factoringbank",
  holder: "Factoring Beispiel GmbH",
  iban_formatted: "AT61 1904 3002 3457 3201",
  is_default: false,
  third_party: true,
};
const francs = { ...own, id: "francs", currency: "CHF" as const };

describe("bank account choice", () => {
  it("offers the accounts of the currency, the default first", () => {
    expect(accountsFor([provider, francs, own], "EUR").map((a) => a.id)).toEqual([
      "own",
      "provider",
    ]);
    expect(offersAccountChoice([provider, francs, own], "EUR")).toBe(true);
    expect(offersAccountChoice([provider, francs, own], "CHF")).toBe(false);
    expect(offersAccountChoice([], "CHF")).toBe(false);
  });

  it("labels accounts briefly", () => {
    expect(shortIban("DE89 3704 0044 0532 0130 00")).toBe("DE89 3704 …");
    expect(shortIban("DE89 3704")).toBe("DE89 3704");
    expect(accountLabel(own, t)).toBe("Musterbank · DE89 3704 … (Standard)");
    expect(accountLabel(provider, t)).toBe("Factoring Beispiel GmbH · AT61 1904 … (Drittkonto)");
    expect(accountLabel({ ...provider, is_default: true }, t)).toBe(
      "Factoring Beispiel GmbH · AT61 1904 … (Drittkonto) (Standard)",
    );
    expect(accountLabel({ ...own, is_default: false }, t)).toBe("Musterbank · DE89 3704 …");
  });

  it("drops a choice that no longer holds", () => {
    const accounts = [own, provider, francs];
    expect(validAccountChoice("", accounts, "EUR")).toBe("");
    expect(validAccountChoice("provider", accounts, "EUR")).toBe("provider");
    expect(validAccountChoice("provider", accounts, "CHF")).toBe("");
    expect(validAccountChoice("gone", accounts, "EUR")).toBe("");
    expect(validAccountChoice("provider", undefined, "CHF")).toBe("provider");
  });
});
