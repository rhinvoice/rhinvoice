import { de, type MessageKey } from "@/lib/i18n/messages.de";
import { en } from "@/lib/i18n/messages.en";
import { fr } from "@/lib/i18n/messages.fr";
import { it } from "@/lib/i18n/messages.it";
import {
  createTranslator,
  mapCatalog,
  toSwissGerman,
  type Catalog,
  type Translate,
} from "@/lib/i18n/translate";
import type { Locale } from "@/lib/locale";

export type { MessageKey } from "@/lib/i18n/messages.de";
export type T = Translate<MessageKey>;

const deCH = mapCatalog<MessageKey>(de, toSwissGerman);

const CATALOGS: Readonly<Record<Locale, Catalog<MessageKey>>> = {
  "de-CH": deCH,
  "de-DE": de,
  "de-AT": de,
  "fr-CH": fr,
  "it-CH": it,
  en,
};

export function translatorFor(locale: Locale): T {
  return createTranslator(CATALOGS[locale], locale);
}

/** Map an API error code onto a translated message if one exists. */
export function errorMessageKey(code: string): MessageKey {
  const key = `error.${code}`;
  return key in de ? (key as MessageKey) : "error.generic";
}
