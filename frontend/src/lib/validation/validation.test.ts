import { describe, expect, it } from "vitest";

import {
  expectedIbanLength,
  formatIban,
  ibanProblem,
  isQrIban,
  isValidBic,
  normalizeIban,
} from "@/lib/validation/iban";
import { vatProblem } from "@/lib/validation/vat-number";

describe("IBAN", () => {
  it.each([
    "CH9300762011623852957",
    "ch93 0076 2011 6238 5295 7",
    "CH4431999123000889012",
    "DE89370400440532013000",
    "AT611904300234573201",
    "LI21088100002324013AA",
  ])("accepts %s", (iban) => {
    expect(ibanProblem(iban)).toBeNull();
  });

  it.each([
    ["", "format"],
    ["9300762011623852957", "format"],
    ["CH93-0076", "format"],
    ["ZZ9300762011623852957", "country"],
    ["CH930076201162385295", "length"],
    ["CH9300762011623852958", "checksum"],
  ] as const)("reports %j as %s", (iban, problem) => {
    expect(ibanProblem(iban)).toBe(problem);
  });

  it("normalises and formats", () => {
    expect(normalizeIban(" ch93 0076 ")).toBe("CH930076");
    expect(formatIban("CH9300762011623852957")).toBe("CH93 0076 2011 6238 5295 7");
    expect(expectedIbanLength("de89")).toBe(22);
    expect(expectedIbanLength("zz")).toBeUndefined();
  });

  it("detects QR-IBANs", () => {
    expect(isQrIban("CH44 3199 9123 0008 8901 2")).toBe(true);
    expect(isQrIban("CH9300762011623852957")).toBe(false);
    expect(isQrIban("DE89370400440532013000")).toBe(false);
    expect(isQrIban("CH4431999123000889013")).toBe(false);
  });

  it("validates BICs", () => {
    expect(isValidBic("UBSWCHZH80A")).toBe(true);
    expect(isValidBic("cobadeff")).toBe(true);
    expect(isValidBic("UBSWCHZH8")).toBe(false);
  });
});

describe("VAT numbers", () => {
  it.each([
    "",
    "CHE-123.456.788",
    "che123456788 mwst",
    "CHE-000.000.000",
    "DE123456789",
    "ATU12345678",
    "FR40303265045",
    "12345",
  ])("accepts %j", (value) => {
    expect(vatProblem(value)).toBeNull();
  });

  it.each([
    ["CHE-123.456.789", "swiss-check-digit"],
    ["CHE-123.456.78", "swiss-format"],
    ["DE12345678", "german-format"],
    ["ATU1234567", "austrian-format"],
    ["AT12345678", "austrian-format"],
  ] as const)("reports %j as %s", (value, problem) => {
    expect(vatProblem(value)).toBe(problem);
  });
});
