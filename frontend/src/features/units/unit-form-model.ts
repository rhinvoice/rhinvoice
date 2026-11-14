import type { Path } from "react-hook-form";
import { z } from "zod";

import { fields } from "@/features/shared/form-schema";
import type { Unit, UnitCode, UnitGroup, UnitOffer, UnitRequest } from "@/features/units/api";
import type { T } from "@/lib/i18n";
import { textFor, type Locale } from "@/lib/locale";

export const MAX_UNIT_LABEL = 20;
export const MAX_UNIT_DESCRIPTION = 100;
/** How many codes the code field suggests at once; typing narrows the list down. */
export const MAX_CODE_SUGGESTIONS = 50;
/** The catalogue's groups in the order the dialog lists them, hidden units of one's own last. */
export const GROUPS = [
  "time",
  "quantity",
  "weight",
  "length",
  "area",
  "volume",
  "energy",
  "packaging",
] as const satisfies readonly UnitGroup[];

/** The rules the server checks on saving (ADR 0046), here as the user types. */
export function unitSchema(t: T, locale: Locale) {
  const f = fields(t, locale);
  return z.object({
    label: f.requiredText(MAX_UNIT_LABEL),
    /** Set by picking from the code list; "" until a code is chosen. */
    code: z.string().min(1, t("units.codeRequired")),
    label_en: f.optionalText(MAX_UNIT_LABEL),
    label_fr: f.optionalText(MAX_UNIT_LABEL),
    label_it: f.optionalText(MAX_UNIT_LABEL),
    description: f.optionalText(MAX_UNIT_DESCRIPTION),
  });
}

export type UnitFormValues = z.infer<ReturnType<typeof unitSchema>>;

export function emptyUnit(): UnitFormValues {
  return { label: "", code: "", label_en: "", label_fr: "", label_it: "", description: "" };
}

export function unitToForm(unit: Unit): UnitFormValues {
  return {
    label: unit.label,
    code: unit.code,
    label_en: unit.labels.en,
    label_fr: unit.labels.fr,
    label_it: unit.labels.it,
    description: unit.description,
  };
}

export function formToRequest(values: UnitFormValues): UnitRequest {
  return {
    label: values.label,
    code: values.code,
    labels: { en: values.label_en, fr: values.label_fr, it: values.label_it },
    description: values.description,
  };
}

/** Whether a unit has a label of its own for English, French or Italian documents. */
export function hasTranslations(values: UnitFormValues): boolean {
  return values.label_en !== "" || values.label_fr !== "" || values.label_it !== "";
}

/** Map API error fields ("labels.en", "label_en") onto form fields. */
export function unitFieldFor(apiField: string): Path<UnitFormValues> | null {
  const field = apiField.replace(/^labels\./, "label_");
  return field in emptyUnit() ? (field as Path<UnitFormValues>) : null;
}

/** How the code field shows a code: "DTN – decitonne". */
export function codeText(code: UnitCode): string {
  return `${code.code} – ${code.name}`;
}

/** The code a typed text names: the code itself or its entry as the field shows it. */
export function codeOf(text: string, codes: readonly UnitCode[]): string {
  const typed = text
    .replace(/ – .*$/, "")
    .trim()
    .toUpperCase();
  return codes.find((code) => code.code === typed)?.code ?? "";
}

/**
 * The codes that fit a search, by code or by name: the code itself first, then the codes
 * that start with it, then the names that contain it.
 */
export function codeSuggestions(codes: readonly UnitCode[], text: string): UnitCode[] {
  const query = text.trim().toLowerCase();
  if (query === "") return codes.slice(0, MAX_CODE_SUGGESTIONS);
  const rank = (code: UnitCode): number => {
    const own = code.code.toLowerCase();
    if (own === query || codeText(code).toLowerCase() === query) return 0;
    if (own.startsWith(query)) return 1;
    return code.name.toLowerCase().includes(query) ? 2 : 3;
  };
  return codes
    .map((code) => ({ code, rank: rank(code) }))
    .filter((entry) => entry.rank < 3)
    .sort((a, b) => a.rank - b.rank)
    .slice(0, MAX_CODE_SUGGESTIONS)
    .map((entry) => entry.code);
}

/** What the catalogue dialog shows of an entry: its label and its name in the interface's language. */
export function offerName(offer: UnitOffer, locale: Locale): string {
  const name =
    offer.key === null && Object.keys(offer.names).length === 0
      ? offer.description
      : textFor(locale, {
          de: offer.names["de"] ?? "",
          en: offer.names["en"] ?? "",
          fr: offer.names["fr"] ?? "",
          it: offer.names["it"] ?? "",
        });
  return name === "" || name === offer.label ? offer.label : `${offer.label} · ${name}`;
}

/** The key the dialog chooses an entry by: the catalogue's key or the hidden unit's id. */
export function offerKey(offer: UnitOffer): string {
  return offer.key ?? `unit:${offer.unit_id ?? ""}`;
}

export interface OfferGroup {
  /** A group of the catalogue; null for hidden units of the user's own. */
  readonly group: UnitGroup | null;
  readonly offers: readonly UnitOffer[];
}

/** The entries that fit the search (label, name or code), grouped as the catalogue groups them. */
export function groupedOffers(
  offers: readonly UnitOffer[],
  search: string,
  locale: Locale,
): OfferGroup[] {
  const query = search.trim().toLowerCase();
  const found = offers.filter(
    (offer) =>
      query === "" ||
      offerName(offer, locale).toLowerCase().includes(query) ||
      offer.code.toLowerCase().includes(query),
  );
  return [...GROUPS, null]
    .map((group) => ({ group, offers: found.filter((offer) => offer.group === group) }))
    .filter((entry) => entry.offers.length > 0);
}

/** What "Take over" sends for the chosen entries. */
export function chosenOffers(
  offers: readonly UnitOffer[],
  chosen: ReadonlySet<string>,
): { readonly keys: string[]; readonly unitIds: string[] } {
  const picked = offers.filter((offer) => chosen.has(offerKey(offer)));
  return {
    keys: picked.flatMap((offer) => (offer.key === null ? [] : [offer.key])),
    unitIds: picked.flatMap((offer) =>
      offer.key === null && offer.unit_id !== null ? [offer.unit_id] : [],
    ),
  };
}
