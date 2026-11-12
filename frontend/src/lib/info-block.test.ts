import { describe, expect, it } from "vitest";

import {
  INFO_ROWS,
  addField,
  customFieldCount,
  entryName,
  fieldValues,
  fieldEntries,
  isField,
  isReferenceField,
  isRow,
  missingReferenceFields,
  move,
  newCustomKey,
  removeField,
  rename,
  setShown,
  type InfoEntry,
} from "@/lib/info-block";
import { translatorFor } from "@/lib/i18n";

const ROWS: readonly InfoEntry[] = INFO_ROWS.map((key) => ({ key, shown: true, label: "" }));
const PROJECT: InfoEntry = { key: "project", shown: true, label: "" };
const OWN: InfoEntry = { key: "custom-0a1b2c3d", shown: true, label: "Objekt" };

describe("the kinds of entries", () => {
  it("tells rows, reference fields and custom fields apart", () => {
    expect(isRow("number")).toBe(true);
    expect(isRow("project")).toBe(false);
    expect(isReferenceField("buyer_accounting")).toBe(true);
    expect(isReferenceField("custom-0a1b2c3d")).toBe(false);
    expect(isReferenceField("toString")).toBe(false);
    expect([ROWS[0], PROJECT, OWN].map((entry) => entry !== undefined && isField(entry))).toEqual([
      false,
      true,
      true,
    ]);
  });

  it("lists the fields in order and counts the custom ones", () => {
    const entries = [OWN, ...ROWS, PROJECT];
    expect(fieldEntries(entries)).toEqual([OWN, PROJECT]);
    expect(customFieldCount(entries)).toBe(1);
    expect(missingReferenceFields(entries)).toEqual([
      "contract",
      "purchase_order",
      "sales_order",
      "despatch_advice",
      "tender",
      "invoiced_object",
      "buyer_accounting",
    ]);
  });
});

describe("changing the block", () => {
  it("adds and removes fields, never rows", () => {
    const added = addField(ROWS, "custom-0a1b2c3d", "Objekt");
    expect(added.at(-1)).toEqual(OWN);
    expect(addField(ROWS, "project")).toEqual([...ROWS, PROJECT]);
    expect(removeField(added, "custom-0a1b2c3d")).toEqual(ROWS);
    expect(removeField(ROWS, "reference")).toEqual(ROWS);
  });

  it("hides rows unless they are required", () => {
    const hidden = setShown(ROWS, "service_date", false);
    expect(hidden.find((entry) => entry.key === "service_date")?.shown).toBe(false);
    expect(setShown(ROWS, "number", false)).toEqual(ROWS);
    expect(setShown([PROJECT], "project", false)).toEqual([PROJECT]);
  });

  it("renames custom fields only", () => {
    expect(rename([OWN], "custom-0a1b2c3d", "Haus")).toEqual([{ ...OWN, label: "Haus" }]);
    expect(rename([PROJECT], "project", "Projekt")).toEqual([PROJECT]);
    expect(rename(ROWS, "number", "Nr.")).toEqual(ROWS);
  });

  it("moves entries within the block", () => {
    const entries = [...ROWS.slice(0, 3)];
    expect(move(entries, 0, 2).map((entry) => entry.key)).toEqual([
      "customer_number",
      "date",
      "number",
    ]);
    expect(move(entries, 2, 0).map((entry) => entry.key)).toEqual([
      "date",
      "number",
      "customer_number",
    ]);
    for (const [from, to] of [
      [1, 1],
      [-1, 0],
      [0, -1],
      [3, 0],
      [0, 3],
    ] as const) {
      expect(move(entries, from, to)).toEqual(entries);
    }
  });

  it("makes custom keys that are new to the block", () => {
    const bytes = [
      [0x0a, 0x1b, 0x2c, 0x3d],
      [0x00, 0x01, 0xfe, 0xff],
    ];
    let call = 0;
    const random = () => new Uint8Array(bytes[call++] ?? []);
    expect(newCustomKey([OWN], random)).toBe("custom-0001feff");
    expect(newCustomKey([])).toMatch(/^custom-[0-9a-f]{8}$/);
  });
});

describe("names", () => {
  it("names rows, reference fields and custom fields", () => {
    const t = translatorFor("de-CH");
    expect(entryName({ key: "service_date", shown: true, label: "" }, t)).toBe(
      "Leistungsdatum oder -zeitraum",
    );
    expect(entryName(PROJECT, t)).toBe("Projekt");
    expect(entryName(OWN, t)).toBe("Objekt");
    expect(entryName({ ...OWN, label: " " }, t)).toBe("Eigenes Feld");
  });

  it("lists a document's values in the layout's order", () => {
    const t = translatorFor("de-CH");
    const values = {
      contract: "V-7",
      "custom-0a1b2c3d": "Haus Nord",
      "custom-99999999": "removed",
      project: "Website",
      buyer_accounting: "",
    };
    expect(
      fieldValues(values, [...ROWS, OWN, PROJECT, PROJECT, { ...OWN, label: "Haus" }], t),
    ).toEqual([
      ["Objekt", "Haus Nord"],
      ["Projekt", "Website"],
      ["Vertragsnummer", "V-7"],
    ]);
    expect(fieldValues({}, [OWN], t)).toEqual([]);
  });
});
