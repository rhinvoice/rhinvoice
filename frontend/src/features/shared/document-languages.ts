import type { components } from "@/api/client";

export type DocumentLanguage = components["schemas"]["Language"];

/** The languages documents can be written in, in the order the selects offer them. */
export const DOCUMENT_LANGUAGES = [
  "de",
  "en",
  "fr",
  "it",
] as const satisfies readonly DocumentLanguage[];
