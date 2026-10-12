import { describe, expect, it } from "vitest";

import {
  containsTemplate,
  defaultTexts,
  switchLanguage,
  templatesFor,
  toggleTemplate,
} from "@/features/documents/document-texts";
import type { TextTemplate } from "@/features/shared/texts-api";

function template(overrides: Partial<TextTemplate>): TextTemplate {
  return {
    id: "t",
    kind: "payment",
    document_type: "invoice",
    language: "de",
    name: "Name",
    text: "Text",
    is_default: false,
    position: 0,
    ...overrides,
  };
}

const due = template({ id: "due", text: "Zahlbar bis {faellig}.", is_default: true, position: 0 });
const reference = template({
  id: "ref",
  text: "Bitte Nummer {nummer}\nals Zweck angeben.",
  is_default: true,
  position: 1,
});
const prompt = template({ id: "prompt", text: "Zahlbar prompt.", position: 2 });
const intro = template({ id: "intro", kind: "intro", text: "Hallo", is_default: true });
const quote = template({ id: "quote", document_type: "quote", text: "Angebot", is_default: true });
const english = template({
  id: "en",
  language: "en",
  text: "Payable by {faellig}.",
  is_default: true,
});
const ALL = [prompt, intro, reference, quote, due, english];
const PAYMENTS = [due, reference, prompt];

describe("templatesFor and defaultTexts", () => {
  it("filters by kind, type and language in their order", () => {
    expect(templatesFor(ALL, "payment", "invoice", "de")).toEqual(PAYMENTS);
    expect(templatesFor(ALL, "payment", "quote", "de")).toEqual([quote]);
    expect(templatesFor(ALL, "closing", "invoice", "de")).toEqual([]);
  });

  it("joins the default templates", () => {
    expect(defaultTexts(ALL, "invoice", "de")).toEqual({
      intro_text: "Hallo",
      payment_text: "Zahlbar bis {faellig}.\nBitte Nummer {nummer}\nals Zweck angeben.",
      closing_text: "",
    });
    expect(defaultTexts(ALL, "invoice", "en").payment_text).toBe("Payable by {faellig}.");
    expect(defaultTexts([], "quote", "de")).toEqual({
      intro_text: "",
      payment_text: "",
      closing_text: "",
    });
  });
});

describe("toggleTemplate", () => {
  it("adds templates in their order and keeps own text at the end", () => {
    expect(toggleTemplate("", prompt, PAYMENTS)).toBe("Zahlbar prompt.");
    expect(toggleTemplate("Zahlbar prompt.\nEigener Text", due, PAYMENTS)).toBe(
      "Zahlbar bis {faellig}.\nZahlbar prompt.\nEigener Text",
    );
  });

  it("removes a template, also one spanning several lines", () => {
    const text = "Zahlbar bis {faellig}.\nBitte Nummer {nummer}\nals Zweck angeben.";
    expect(toggleTemplate(text, reference, PAYMENTS)).toBe("Zahlbar bis {faellig}.");
    expect(toggleTemplate(text, due, PAYMENTS)).toBe("Bitte Nummer {nummer}\nals Zweck angeben.");
    expect(toggleTemplate("Zahlbar prompt.", prompt, PAYMENTS)).toBe("");
  });

  it("only matches whole lines", () => {
    expect(containsTemplate("Zahlbar prompt. Sofort", prompt)).toBe(false);
    expect(containsTemplate("Vorher\nZahlbar prompt.", prompt)).toBe(true);
    expect(containsTemplate("Bitte Nummer {nummer}", reference)).toBe(false);
    expect(containsTemplate("", template({ text: "" }))).toBe(false);
    expect(toggleTemplate("Bitte Nummer {nummer}", reference, PAYMENTS)).toBe(
      "Bitte Nummer {nummer}\nals Zweck angeben.\nBitte Nummer {nummer}",
    );
  });
});

describe("switchLanguage", () => {
  it("replaces untouched defaults and keeps changed texts", () => {
    const german = defaultTexts(ALL, "invoice", "de");
    expect(switchLanguage(german, ALL, "invoice", "de", "en")).toEqual({
      intro_text: "",
      payment_text: "Payable by {faellig}.",
      closing_text: "",
    });
    const changed = { ...german, intro_text: "Guten Tag" };
    expect(switchLanguage(changed, ALL, "invoice", "de", "en").intro_text).toBe("Guten Tag");
  });
});
