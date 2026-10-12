/**
 * Compare and add canonical decimal strings ("1234.5", "-0.05") exactly,
 * without floating point. Invoices are calculated by the server only; the
 * frontend compares amounts for input checks and adds amounts the server
 * calculated for display, e.g. the open sum of the selected invoices.
 */
const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

function scaled(value: string, places: number): bigint {
  const match = DECIMAL.exec(value);
  if (match === null) {
    throw new RangeError(`not a decimal: ${value}`);
  }
  const [, sign = "", integer = "0", fraction = ""] = match;
  const digits = BigInt(integer + fraction.padEnd(places, "0"));
  return sign === "-" ? -digits : digits;
}

function places(value: string): number {
  return value.split(".")[1]?.length ?? 0;
}

export function compareDecimal(a: string, b: string): -1 | 0 | 1 {
  const precision = Math.max(places(a), places(b));
  const left = scaled(a, precision);
  const right = scaled(b, precision);
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

/** Exact sum of decimal strings, with as many decimal places as the most precise one. */
export function addDecimals(values: readonly string[]): string {
  const precision = Math.max(0, ...values.map(places));
  const total = values.reduce((sum, value) => sum + scaled(value, precision), 0n);
  const negative = total < 0n;
  const digits = (negative ? -total : total).toString().padStart(precision + 1, "0");
  const integer = digits.slice(0, digits.length - precision);
  const fraction = precision === 0 ? "" : `.${digits.slice(digits.length - precision)}`;
  return `${negative ? "-" : ""}${integer}${fraction}`;
}
