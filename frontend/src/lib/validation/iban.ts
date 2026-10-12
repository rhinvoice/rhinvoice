/**
 * IBAN checks for immediate feedback in forms. The backend validates again
 * (rhinvoice.domain.shared.iban); lengths from the SWIFT IBAN Registry.
 */
const IBAN_LENGTHS: Readonly<Record<string, number>> = {
  AD: 24,
  AE: 23,
  AL: 28,
  AT: 20,
  AZ: 28,
  BA: 20,
  BE: 16,
  BG: 22,
  BH: 22,
  BI: 27,
  BR: 29,
  BY: 28,
  CH: 21,
  CR: 22,
  CY: 28,
  CZ: 24,
  DE: 22,
  DJ: 27,
  DK: 18,
  DO: 28,
  EE: 20,
  EG: 29,
  ES: 24,
  FI: 18,
  FK: 18,
  FO: 18,
  FR: 27,
  GB: 22,
  GE: 22,
  GI: 23,
  GL: 18,
  GR: 27,
  GT: 28,
  HN: 28,
  HR: 21,
  HU: 28,
  IE: 22,
  IL: 23,
  IQ: 23,
  IS: 26,
  IT: 27,
  JO: 30,
  KW: 30,
  KZ: 20,
  LB: 28,
  LC: 32,
  LI: 21,
  LT: 20,
  LU: 20,
  LV: 21,
  LY: 25,
  MC: 27,
  MD: 24,
  ME: 22,
  MK: 19,
  MN: 20,
  MR: 27,
  MT: 31,
  MU: 30,
  NI: 28,
  NL: 18,
  NO: 15,
  OM: 23,
  PK: 24,
  PL: 28,
  PS: 29,
  PT: 25,
  QA: 29,
  RO: 24,
  RS: 22,
  RU: 33,
  SA: 24,
  SC: 31,
  SD: 18,
  SE: 24,
  SI: 19,
  SK: 24,
  SM: 27,
  SO: 23,
  ST: 25,
  SV: 28,
  TL: 23,
  TN: 24,
  TR: 26,
  UA: 29,
  VA: 22,
  VG: 24,
  XK: 20,
  YE: 30,
};

export type IbanProblem = "format" | "country" | "length" | "checksum";

export function normalizeIban(raw: string): string {
  return raw.replace(/\s+/g, "").toUpperCase();
}

function mod97(iban: string): number {
  const rearranged = iban.slice(4) + iban.slice(0, 4);
  let remainder = 0;
  for (const char of rearranged) {
    const value = Number.parseInt(char, 36).toString();
    for (const digit of value) {
      remainder = (remainder * 10 + Number(digit)) % 97;
    }
  }
  return remainder;
}

/** Return the first problem of an IBAN, or null when it is valid. */
export function ibanProblem(raw: string): IbanProblem | null {
  const iban = normalizeIban(raw);
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]+$/.test(iban)) {
    return "format";
  }
  const expected = IBAN_LENGTHS[iban.slice(0, 2)];
  if (expected === undefined) {
    return "country";
  }
  if (iban.length !== expected) {
    return "length";
  }
  return mod97(iban) === 1 ? null : "checksum";
}

export function expectedIbanLength(raw: string): number | undefined {
  return IBAN_LENGTHS[normalizeIban(raw).slice(0, 2)];
}

/** Swiss/Liechtenstein QR-IBAN: institution id 30000-31999. */
export function isQrIban(raw: string): boolean {
  const iban = normalizeIban(raw);
  if (!["CH", "LI"].includes(iban.slice(0, 2)) || ibanProblem(iban) !== null) {
    return false;
  }
  const iid = Number(iban.slice(4, 9));
  return iid >= 30000 && iid <= 31999;
}

/** Group an IBAN in blocks of four for display. */
export function formatIban(raw: string): string {
  return normalizeIban(raw).replace(/(.{4})(?=.)/g, "$1 ");
}

export function isValidBic(raw: string): boolean {
  return /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/.test(raw.replace(/\s+/g, "").toUpperCase());
}
