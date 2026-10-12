import { describe, expect, it } from "vitest";

import { errorMessageKey, translatorFor } from "@/lib/i18n";
import { de } from "@/lib/i18n/messages.de";
import { en } from "@/lib/i18n/messages.en";
import { createTranslator, mapCatalog, toSwissGerman } from "@/lib/i18n/translate";

describe("translator", () => {
  it("interpolates values and keeps unknown placeholders", () => {
    const t = createTranslator({ greet: "Hallo {name}, {missing}" }, "de-DE");
    expect(t("greet", { name: "Anna" })).toBe("Hallo Anna, {missing}");
    expect(t("greet")).toBe("Hallo {name}, {missing}");
  });

  it("selects plural forms", () => {
    const t = createTranslator(
      {
        invoices: { zero: "Keine Rechnungen", one: "1 Rechnung", other: "{count} Rechnungen" },
        items: { one: "1 item", other: "{count} items" },
      },
      "de-DE",
    );
    expect(t("invoices", { count: 0 })).toBe("Keine Rechnungen");
    expect(t("invoices", { count: 1 })).toBe("1 Rechnung");
    expect(t("invoices", { count: 3 })).toBe("3 Rechnungen");
    expect(t("items", { count: 0 })).toBe("0 items");
    expect(t("items")).toBe("{count} items");
  });

  it("derives Swiss German without ß", () => {
    expect(toSwissGerman("Straße, gemäß, schließen")).toBe("Strasse, gemäss, schliessen");
    const mapped = mapCatalog(
      {
        a: "Maß",
        b: { one: "ein Fuß", other: "{count} Füße" },
        c: { zero: "ß", one: "", other: "" },
      },
      toSwissGerman,
    );
    expect(mapped).toEqual({
      a: "Mass",
      b: { one: "ein Fuss", other: "{count} Füsse" },
      c: { zero: "ss", one: "", other: "" },
    });
  });

  it("provides a translator per locale", () => {
    expect(translatorFor("de-CH")("common.close")).toBe("Schliessen");
    expect(translatorFor("de-DE")("common.close")).toBe("Schließen");
    expect(translatorFor("de-AT")("common.close")).toBe("Schließen");
    expect(translatorFor("en")("common.close")).toBe("Close");
    expect(translatorFor("de-CH")("validation.summary", { count: 2 })).toBe(
      "2 Angaben müssen korrigiert werden",
    );
  });

  it("has the same keys in every catalog", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(de).sort());
  });

  it("does not use ß in English and never leaves empty texts", () => {
    for (const message of [...Object.values(de), ...Object.values(en)]) {
      const texts = typeof message === "string" ? [message] : [message.one, message.other];
      for (const text of texts) {
        expect(text.trim()).not.toBe("");
      }
    }
    expect(JSON.stringify(en)).not.toContain("ß");
  });

  it("maps API error codes to messages", () => {
    expect(errorMessageKey("account_locked")).toBe("error.account_locked");
    expect(errorMessageKey("something_else")).toBe("error.generic");
  });
});
