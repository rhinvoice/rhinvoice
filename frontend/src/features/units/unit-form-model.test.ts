import { describe, expect, it } from "vitest";

import type { UnitCode, UnitOffer } from "@/features/units/api";
import {
  chosenOffers,
  codeOf,
  codeSuggestions,
  codeText,
  emptyUnit,
  formToRequest,
  groupedOffers,
  hasTranslations,
  MAX_CODE_SUGGESTIONS,
  offerKey,
  offerName,
  unitFieldFor,
  unitSchema,
  unitToForm,
  type UnitFormValues,
} from "@/features/units/unit-form-model";
import { translatorFor } from "@/lib/i18n";
import { unitAt } from "@/test/units";

const t = translatorFor("de-CH");
const schema = unitSchema(t, "de-CH");

function issues(values: UnitFormValues): Record<string, string> {
  const result = schema.safeParse(values);
  if (result.success) return {};
  return Object.fromEntries(
    result.error.issues.map((issue) => [issue.path.join("."), issue.message]),
  );
}

const CODES: readonly UnitCode[] = [
  { code: "C62", name: "one" },
  { code: "DTN", name: "decitonne" },
  { code: "H18", name: "square hectometre" },
  { code: "HUR", name: "hour" },
  { code: "TNE", name: "tonne (metric ton)" },
];

const QUINTAL: UnitOffer = {
  key: "DTN",
  unit_id: null,
  group: "weight",
  code: "DTN",
  label: "dz",
  names: {
    de: "Doppelzentner (100 kg)",
    en: "decitonne (100 kg)",
    fr: "quintal (100 kg)",
    it: "quintale (100 kg)",
  },
  description: "",
};
const HECTARE: UnitOffer = {
  ...QUINTAL,
  key: "H18",
  group: "area",
  code: "H18",
  label: "ha",
  names: { de: "Hektar", en: "hectare", fr: "hectare", it: "ettaro" },
};
const HOURS: UnitOffer = {
  ...QUINTAL,
  key: null,
  unit_id: "unit-hours",
  group: "time",
  code: "HUR",
  label: "Std.",
  names: { de: "Stunde", en: "hour", fr: "heure", it: "ora" },
};
const OWN: UnitOffer = {
  key: null,
  unit_id: "unit-own",
  group: null,
  code: "XPX",
  label: "Palette",
  names: {},
  description: "Euro-Palette",
};
const SET: UnitOffer = { ...QUINTAL, key: "SET", code: "SET", label: "Set", names: {} };

describe("the unit form", () => {
  it("checks label, code and lengths", () => {
    expect(issues({ ...emptyUnit(), label: "dz", code: "DTN" })).toEqual({});
    expect(issues(emptyUnit())).toEqual({
      label: t("validation.required"),
      code: t("units.codeRequired"),
    });
    const long = "x".repeat(21);
    expect(
      Object.keys(
        issues({
          label: long,
          code: "DTN",
          label_en: long,
          label_fr: long,
          label_it: long,
          description: "x".repeat(101),
        }),
      ),
    ).toEqual(["label", "label_en", "label_fr", "label_it", "description"]);
    const longest = { label: "x".repeat(20), description: "x".repeat(100) };
    expect(issues({ ...emptyUnit(), code: "DTN", ...longest })).toEqual({});
  });

  it("round-trips a unit through the API's shape", () => {
    const quintal = unitAt(3);
    const form = unitToForm(quintal);
    expect(form).toEqual({
      label: "dz",
      code: "DTN",
      label_en: "dt",
      label_fr: "q",
      label_it: "q",
      description: "Doppelzentner (100 kg)",
    });
    expect(formToRequest(form)).toEqual({
      label: "dz",
      code: "DTN",
      labels: { en: "dt", fr: "q", it: "q" },
      description: "Doppelzentner (100 kg)",
    });
  });

  it("knows whether a unit has labels of its own for other languages", () => {
    expect(hasTranslations(emptyUnit())).toBe(false);
    expect(hasTranslations({ ...emptyUnit(), label_en: "dt" })).toBe(true);
    expect(hasTranslations({ ...emptyUnit(), label_fr: "q" })).toBe(true);
    expect(hasTranslations({ ...emptyUnit(), label_it: "q" })).toBe(true);
  });

  it("maps the server's fields onto the form", () => {
    expect(unitFieldFor("label")).toBe("label");
    expect(unitFieldFor("code")).toBe("code");
    expect(unitFieldFor("labels.en")).toBe("label_en");
    expect(unitFieldFor("label_it")).toBe("label_it");
    expect(unitFieldFor("description")).toBe("description");
    expect(unitFieldFor("unit_ids")).toBeNull();
  });
});

describe("the code field", () => {
  it("shows a code with its name and reads it back", () => {
    expect(codeText({ code: "DTN", name: "decitonne" })).toBe("DTN – decitonne");
    expect(codeOf("DTN – decitonne", CODES)).toBe("DTN");
    expect(codeOf(" dtn ", CODES)).toBe("DTN");
    expect(codeOf("decitonne", CODES)).toBe("");
    expect(codeOf("HAR", CODES)).toBe("");
    expect(codeOf("", CODES)).toBe("");
  });

  it("suggests the code first, then codes starting with it, then names", () => {
    expect(codeSuggestions(CODES, "h").map((code) => code.code)).toEqual(["H18", "HUR"]);
    expect(codeSuggestions(CODES, "hur").map((code) => code.code)).toEqual(["HUR"]);
    expect(codeSuggestions(CODES, "tonne").map((code) => code.code)).toEqual(["DTN", "TNE"]);
    expect(codeSuggestions(CODES, "T").map((code) => code.code)).toEqual(["TNE", "DTN", "H18"]);
    expect(codeSuggestions(CODES, "DTN – decitonne").map((code) => code.code)).toEqual(["DTN"]);
    expect(codeSuggestions(CODES, "xyz")).toEqual([]);
    expect(codeSuggestions(CODES, " ")).toEqual(CODES);
    const many = Array.from({ length: 80 }, (_, index) => ({
      code: `A${String(index)}`,
      name: "unit",
    }));
    expect(codeSuggestions(many, "")).toHaveLength(MAX_CODE_SUGGESTIONS);
    expect(codeSuggestions(many, "unit")).toHaveLength(MAX_CODE_SUGGESTIONS);
  });
});

describe("the catalogue", () => {
  it("names an entry by its label and its name in the interface's language", () => {
    expect(offerName(QUINTAL, "de-CH")).toBe("dz · Doppelzentner (100 kg)");
    expect(offerName(QUINTAL, "fr-CH")).toBe("dz · quintal (100 kg)");
    expect(offerName(HOURS, "en")).toBe("Std. · hour");
    // A hidden unit of one's own: its description; a name like the label once.
    expect(offerName(OWN, "de-CH")).toBe("Palette · Euro-Palette");
    expect(offerName({ ...OWN, description: "" }, "de-CH")).toBe("Palette");
    expect(offerName(SET, "de-CH")).toBe("Set");
    expect(offerName({ ...HECTARE, label: "Hektar" }, "de-CH")).toBe("Hektar");
  });

  it("groups and searches the entries", () => {
    const offers = [HOURS, QUINTAL, OWN, HECTARE];
    expect(groupedOffers(offers, "", "de-CH")).toEqual([
      { group: "time", offers: [HOURS] },
      { group: "weight", offers: [QUINTAL] },
      { group: "area", offers: [HECTARE] },
      { group: null, offers: [OWN] },
    ]);
    expect(groupedOffers(offers, " doppel", "de-CH")).toEqual([
      { group: "weight", offers: [QUINTAL] },
    ]);
    expect(groupedOffers(offers, "h18", "de-CH")).toEqual([{ group: "area", offers: [HECTARE] }]);
    expect(groupedOffers(offers, "euro", "de-CH")).toEqual([{ group: null, offers: [OWN] }]);
    expect(groupedOffers(offers, "fass", "de-CH")).toEqual([]);
  });

  it("sends the chosen entries and hidden units", () => {
    expect([offerKey(QUINTAL), offerKey(HOURS)]).toEqual(["DTN", "unit:unit-hours"]);
    expect(offerKey({ ...HOURS, unit_id: null })).toBe("unit:");
    const offers = [HOURS, QUINTAL, OWN, HECTARE];
    expect(chosenOffers(offers, new Set(["DTN", "unit:unit-own", "unit:unit-hours"]))).toEqual({
      keys: ["DTN"],
      unitIds: ["unit-hours", "unit-own"],
    });
    expect(chosenOffers(offers, new Set())).toEqual({ keys: [], unitIds: [] });
    expect(chosenOffers([{ ...HOURS, unit_id: null }], new Set(["unit:"]))).toEqual({
      keys: [],
      unitIds: [],
    });
  });
});
