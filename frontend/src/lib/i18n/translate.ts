import type { Locale } from "@/lib/locale";

export interface PluralMessage {
  readonly one: string;
  readonly other: string;
  readonly zero?: string;
}
export type Message = string | PluralMessage;
export type Catalog<K extends string> = Readonly<Record<K, Message>>;
export type Values = Readonly<Record<string, string | number>>;

const PLACEHOLDER = /\{(\w+)\}/g;

function interpolate(template: string, values: Values): string {
  return template.replace(PLACEHOLDER, (match, name: string) => {
    const value = values[name];
    return value === undefined ? match : String(value);
  });
}

function selectPlural(message: PluralMessage, count: number, rules: Intl.PluralRules): string {
  if (count === 0 && message.zero !== undefined) {
    return message.zero;
  }
  return rules.select(count) === "one" ? message.one : message.other;
}

/** Swiss Standard German does not use "ß". */
export function toSwissGerman(text: string): string {
  return text.replaceAll("ß", "ss");
}

export type Translate<K extends string> = (key: K, values?: Values) => string;

export function createTranslator<K extends string>(
  catalog: Catalog<K>,
  locale: Locale,
): Translate<K> {
  const rules = new Intl.PluralRules(locale);
  return (key, values = {}) => {
    const message = catalog[key];
    const template =
      typeof message === "string"
        ? message
        : selectPlural(message, Number(values["count"] ?? 0), rules);
    return interpolate(template, values);
  };
}

/** Derive a catalog by applying a text transformation to every message. */
export function mapCatalog<K extends string>(
  catalog: Catalog<K>,
  transform: (text: string) => string,
): Catalog<K> {
  const entries = Object.entries(catalog) as [K, Message][];
  return Object.fromEntries(
    entries.map(([key, message]) => [
      key,
      typeof message === "string"
        ? transform(message)
        : {
            one: transform(message.one),
            other: transform(message.other),
            ...(message.zero === undefined ? {} : { zero: transform(message.zero) }),
          },
    ]),
  ) as Catalog<K>;
}
