/** The facts next to the address on documents: rows of Rhinvoice and fields (#62, #60). */

import type { T } from "@/lib/i18n";

export interface InfoEntry {
  readonly key: string;
  readonly shown: boolean;
  readonly label: string;
}

/** Rows that Rhinvoice fills in itself; each one is listed once. */
export const INFO_ROWS = [
  "number",
  "customer_number",
  "date",
  "due_date",
  "service_date",
  "reference",
] as const;
export type InfoRow = (typeof INFO_ROWS)[number];

/** Rows that every document shows. */
export const REQUIRED_ROWS: ReadonlySet<string> = new Set<InfoRow>(["number", "date"]);

/** Fields with a value per document that the e-invoice carries too, with their business term. */
export const REFERENCE_FIELDS = {
  project: "BT-11",
  contract: "BT-12",
  purchase_order: "BT-13",
  sales_order: "BT-14",
  despatch_advice: "BT-16",
  tender: "BT-17",
  invoiced_object: "BT-18",
  buyer_accounting: "BT-19",
} as const;
export type ReferenceField = keyof typeof REFERENCE_FIELDS;

/** Fields of the user's own, besides the six rows and the eight reference fields. */
export const MAX_CUSTOM_FIELDS = 10;
export const MAX_FIELD_LABEL = 40;
export const MAX_FIELD_VALUE = 100;

const ROW_KEYS: ReadonlySet<string> = new Set(INFO_ROWS);

export function isRow(key: string): key is InfoRow {
  return ROW_KEYS.has(key);
}

export function isReferenceField(key: string): key is ReferenceField {
  return Object.hasOwn(REFERENCE_FIELDS, key);
}

/** Whether the entry is a field with a value per document (a reference or a custom one). */
export function isField(entry: InfoEntry): boolean {
  return !isRow(entry.key);
}

/** The reference fields the block does not list yet, in their usual order. */
export function missingReferenceFields(entries: readonly InfoEntry[]): ReferenceField[] {
  const listed = new Set(entries.map((entry) => entry.key));
  return (Object.keys(REFERENCE_FIELDS) as ReferenceField[]).filter((key) => !listed.has(key));
}

export function customFieldCount(entries: readonly InfoEntry[]): number {
  return entries.filter((entry) => isField(entry) && !isReferenceField(entry.key)).length;
}

/** A new key for a field of the user's own: "custom-" and 8 hex digits, unique in the block. */
export function newCustomKey(
  entries: readonly InfoEntry[],
  random: () => Uint8Array = () => crypto.getRandomValues(new Uint8Array(4)),
): string {
  const taken = new Set(entries.map((entry) => entry.key));
  for (;;) {
    const hex = Array.from(random(), (byte) => byte.toString(16).padStart(2, "0")).join("");
    const key = `custom-${hex}`;
    if (!taken.has(key)) return key;
  }
}

/** Add a field at the end of the block. */
export function addField(entries: readonly InfoEntry[], key: string, label = ""): InfoEntry[] {
  return [...entries, { key, shown: true, label }];
}

export function removeField(entries: readonly InfoEntry[], key: string): InfoEntry[] {
  return entries.filter((entry) => entry.key !== key || isRow(key));
}

/** Show or hide a row; the required ones always stay shown. */
export function setShown(entries: readonly InfoEntry[], key: string, shown: boolean): InfoEntry[] {
  return entries.map((entry) =>
    entry.key === key && isRow(key) && !REQUIRED_ROWS.has(key) ? { ...entry, shown } : entry,
  );
}

export function rename(entries: readonly InfoEntry[], key: string, label: string): InfoEntry[] {
  return entries.map((entry) =>
    entry.key === key && isField(entry) && !isReferenceField(key) ? { ...entry, label } : entry,
  );
}

/** Move the entry at ``from`` to ``to``; out of range leaves the block as it is. */
export function move(entries: readonly InfoEntry[], from: number, to: number): InfoEntry[] {
  const count = entries.length;
  if (from === to || from < 0 || to < 0 || from >= count || to >= count) return [...entries];
  const moved = entries.filter((_, index) => index !== from);
  moved.splice(to, 0, ...entries.slice(from, from + 1));
  return moved;
}

/** The fields whose values a document prints, in order. */
export function fieldEntries(entries: readonly InfoEntry[]): InfoEntry[] {
  return entries.filter(isField);
}

/** The name of an entry as the settings and the editor show it. */
export function entryName(entry: InfoEntry, t: T): string {
  if (isRow(entry.key)) return t(`printLayout.row.${entry.key}`);
  if (isReferenceField(entry.key)) return t(`printLayout.field.${entry.key}`);
  return entry.label.trim() === "" ? t("printLayout.customDefault") : entry.label;
}

/**
 * The values of a document's fields with their names, in the layouts' order (first one wins).
 *
 * Reference fields are named even when the layout no longer lists them; a custom field is
 * named by the layout only, so one removed since is left out (its PDF still shows it).
 */
export function fieldValues(
  values: Readonly<Record<string, string>>,
  entries: readonly InfoEntry[],
  t: T,
): [string, string][] {
  const known = new Set<string>();
  const listed = fieldEntries(entries).filter((entry) => {
    const first = !known.has(entry.key);
    known.add(entry.key);
    return first;
  });
  const others = Object.keys(values)
    .filter((key) => !known.has(key) && isReferenceField(key))
    .map((key): InfoEntry => ({ key, shown: true, label: "" }));
  return [...listed, ...others].flatMap((entry): [string, string][] => {
    const value = values[entry.key] ?? "";
    return value === "" ? [] : [[entryName(entry, t), value]];
  });
}
