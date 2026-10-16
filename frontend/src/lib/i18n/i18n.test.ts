import { describe, expect, it } from "vitest";

import { errorMessageKey, translatorFor } from "@/lib/i18n";
import { de } from "@/lib/i18n/messages.de";
import { en } from "@/lib/i18n/messages.en";
import { fr } from "@/lib/i18n/messages.fr";
import { it as italian } from "@/lib/i18n/messages.it";
import {
  createTranslator,
  mapCatalog,
  toSwissGerman,
  type Catalog,
  type Message,
} from "@/lib/i18n/translate";

const TRANSLATIONS: readonly [string, Catalog<keyof typeof de>][] = [
  ["en", en],
  ["fr", fr],
  ["it", italian],
];

function formsOf(message: Message): Readonly<Record<string, string>> {
  return typeof message === "string" ? { text: message } : { ...message };
}

function placeholdersOf(text: string): string[] {
  return [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1] ?? "").sort();
}

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
    expect(translatorFor("fr-CH")("common.close")).toBe("Fermer");
    expect(translatorFor("it-CH")("common.close")).toBe("Chiudi");
    expect(translatorFor("de-CH")("validation.summary", { count: 2 })).toBe(
      "2 Angaben müssen korrigiert werden",
    );
  });

  it("has the same keys in every catalog", () => {
    for (const catalog of [en, fr, italian]) {
      expect(Object.keys(catalog).sort()).toEqual(Object.keys(de).sort());
    }
  });

  it("keeps placeholders and plural forms of the German texts", () => {
    for (const [name, catalog] of TRANSLATIONS) {
      for (const [key, source] of Object.entries(de) as [keyof typeof de, Message][]) {
        const forms = formsOf(source);
        const target = catalog[key];
        expect(Object.keys(formsOf(target)), `${name} ${key}`).toEqual(Object.keys(forms));
        for (const [form, text] of Object.entries(forms)) {
          const translated = formsOf(target)[form] ?? "";
          // French says "one" for 0 too, so its "one" may need the count the German lacks.
          const expected =
            name === "fr" && form === "one" && placeholdersOf(translated).includes("count")
              ? [...new Set([...placeholdersOf(text), "count"])].sort()
              : placeholdersOf(text);
          expect(placeholdersOf(translated), `${name} ${key} ${form}`).toEqual(expected);
        }
      }
    }
  });

  it("counts in the French singular when it also stands for zero", () => {
    for (const [key, message] of Object.entries(fr)) {
      if (typeof message !== "string" && message.zero === undefined) {
        expect(message.one.includes("{count}") || !message.other.includes("{count}"), key).toBe(
          true,
        );
      }
    }
    expect(translatorFor("fr-CH")("validation.summary", { count: 0 })).toMatch(/^0 /);
  });

  it("does not use ß outside German and never leaves empty texts", () => {
    const catalogs: readonly Catalog<keyof typeof de>[] = [de, en, fr, italian];
    for (const message of catalogs.flatMap((catalog) => Object.values(catalog))) {
      for (const text of Object.values(formsOf(message))) {
        expect(text.trim()).not.toBe("");
      }
    }
    for (const catalog of [en, fr, italian]) {
      expect(JSON.stringify(catalog)).not.toContain("ß");
    }
  });

  it("maps API error codes to messages", () => {
    expect(errorMessageKey("account_locked")).toBe("error.account_locked");
    expect(errorMessageKey("something_else")).toBe("error.generic");
  });
});
