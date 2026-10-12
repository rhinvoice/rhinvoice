import type { Locale } from "@/lib/locale";

/** Separators that can only ever mean "thousands": spaces and apostrophes. */
const UNAMBIGUOUS_GROUPING = /[\s'\u2019\u00a0\u202f]/g;

type Separator = "." | ",";

function localeDecimal(locale: Locale): Separator {
  return locale === "de-DE" || locale === "de-AT" ? "," : ".";
}

function other(separator: Separator): Separator {
  return separator === "." ? "," : ".";
}

function count(text: string, separator: Separator): number {
  return text.split(separator).length - 1;
}

/**
 * Decide which character is the decimal separator.
 *
 * - Both "." and "," present: the last one is the decimal separator.
 * - One kind, several times: it groups thousands ("1.234.567").
 * - One kind, once: the locale's decimal separator is decimal. The other one is
 *   decimal too unless exactly three digits follow ("1,5" in de-CH is 1.5,
 *   "1,234" is 1234) – people often type the "wrong" separator.
 */
function decimalSeparator(body: string, locale: Locale): Separator | null {
  const lastDot = body.lastIndexOf(".");
  const lastComma = body.lastIndexOf(",");
  if (lastDot >= 0 && lastComma >= 0) {
    return lastDot > lastComma ? "." : ",";
  }
  if (lastDot < 0 && lastComma < 0) {
    return null;
  }
  const separator: Separator = lastDot >= 0 ? "." : ",";
  if (count(body, separator) > 1) {
    return null;
  }
  if (separator === localeDecimal(locale)) {
    return separator;
  }
  const digitsAfter = body.length - body.lastIndexOf(separator) - 1;
  return digitsAfter === 3 ? null : separator;
}

/** Thousands groups must be 1-3 digits followed by groups of exactly 3 digits. */
function validGrouping(integer: string, group: Separator): boolean {
  const groups = integer.split(group);
  if (groups.length === 1) {
    return /^\d*$/.test(integer);
  }
  const [first = "", ...rest] = groups;
  return /^\d{1,3}$/.test(first) && rest.every((part) => /^\d{3}$/.test(part));
}

/**
 * Parse user input such as "1’234.50", "1.234,50", "1,5" or "12" into a canonical
 * decimal string ("1234.50"). Returns null for anything that is not clearly a
 * number, so that callers can show a validation message instead of guessing.
 */
export function parseDecimal(input: string, locale: Locale): string | null {
  const text = input.trim().replace(UNAMBIGUOUS_GROUPING, "");
  if (!/^[-+]?[\d.,]+$/.test(text)) {
    return null;
  }
  const negative = text.startsWith("-");
  const body = text.replace(/^[-+]/, "");
  const decimal = decimalSeparator(body, locale);
  const group = decimal === null ? (body.includes(".") ? "." : ",") : other(decimal);
  const [integerPart, fraction] =
    decimal === null
      ? [body, undefined]
      : [body.slice(0, body.lastIndexOf(decimal)), body.slice(body.lastIndexOf(decimal) + 1)];
  // The fraction follows the last separator, so it consists of digits only.
  if (!validGrouping(integerPart, group)) {
    return null;
  }
  const integerDigits = integerPart.split(group).join("");
  if (integerDigits === "" && (fraction === undefined || fraction === "")) {
    return null;
  }
  const integer = (integerDigits === "" ? "0" : integerDigits).replace(/^0+(?=\d)/, "");
  const result = fraction === undefined || fraction === "" ? integer : `${integer}.${fraction}`;
  return negative && /[1-9]/.test(result) ? `-${result}` : result;
}
