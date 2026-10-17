import { describe, expect, it } from "vitest";

import {
  formatDate,
  formatDecimalInput,
  formatDateTime,
  formatMoney,
  formatMonth,
  formatNumber,
  formatChange,
  formatPercent,
  formatRelative,
  formatBytes,
} from "@/lib/format";

/** Normalise the special spaces and apostrophes Intl uses so tests stay readable. */
function plain(text: string): string {
  return text.replace(/[\u00a0\u202f]/g, " ").replace(/\u2019/g, "'");
}

describe("formatMoney", () => {
  it.each([
    ["de-CH", "1234567.5", "CHF", "CHF 1'234'567.50"],
    ["de-DE", "1234567.5", "EUR", "1.234.567,50 EUR"],
    ["de-AT", "1234567.5", "EUR", "EUR 1.234.567,50"],
    ["en", "1234.5", "EUR", "EUR 1,234.50"],
    ["de-CH", "-0.05", "CHF", "CHF-0.05"],
    ["fr-CH", "1234.5", "CHF", "CHF 1'234.50"],
    ["it-CH", "1234.5", "EUR", "EUR 1'234.50"],
  ] as const)("%s %s %s", (locale, amount, currency, expected) => {
    expect(plain(formatMoney(amount, currency, locale))).toBe(expected);
  });

  it("keeps decimal precision of large string amounts", () => {
    expect(plain(formatMoney("123456789012.35", "CHF", "de-CH"))).toBe("CHF 123'456'789'012.35");
  });

  it("shows up to four decimals for unit prices", () => {
    expect(plain(formatMoney("1.2345", "EUR", "de-CH", 4))).toBe("EUR 1.2345");
    expect(plain(formatMoney("150", "CHF", "de-CH", 4))).toBe("CHF 150.00");
  });

  it("reuses cached formatters", () => {
    expect(formatMoney("1", "CHF", "de-CH")).toBe(formatMoney("1", "CHF", "de-CH"));
  });
});

describe("formatDecimalInput", () => {
  it("formats values for editing without grouping", () => {
    expect(formatDecimalInput("1234.5", "de-CH")).toBe("1234.50");
    expect(formatDecimalInput("1234.5678", "de-DE")).toBe("1234,5678");
    expect(formatDecimalInput("2.5", "de-AT", 0, 2)).toBe("2,5");
    expect(formatDecimalInput("10", "en", 0, 2)).toBe("10");
    expect(formatDecimalInput("1234.5", "fr-CH")).toBe("1234.50");
  });
});

describe("formatNumber and formatPercent", () => {
  it("formats quantities", () => {
    expect(plain(formatNumber("1234.5", "de-CH"))).toBe("1'234.5");
    expect(plain(formatNumber("1234.5", "de-AT"))).toBe("1 234,5");
    expect(formatNumber("1.23456", "en")).toBe("1.235");
    expect(formatNumber("1.23456", "en", 1)).toBe("1.2");
    expect(plain(formatNumber("1234.5", "fr-CH"))).toBe("1'234.5");
    expect(plain(formatNumber("1234.5", "it-CH"))).toBe("1'234.5");
  });

  it("formats percentages given in percent points", () => {
    expect(formatPercent("8.1", "de-CH")).toBe("8.1%");
    expect(plain(formatPercent("8.1", "de-DE"))).toBe("8,1 %");
    expect(formatPercent("2.6", "en")).toBe("2.6%");
    expect(formatPercent("8.1", "fr-CH")).toBe("8.1%");
  });
});

describe("formatDate", () => {
  it("formats medium and long dates without timezone shifts", () => {
    expect(formatDate("2026-01-05", "de-CH")).toBe("05.01.2026");
    expect(formatDate("2026-01-05", "de-AT", "long")).toBe("5. Jänner 2026");
    expect(formatDate("2026-01-05", "de-DE", "long")).toBe("5. Januar 2026");
    expect(formatDate("2026-01-05T23:30:00Z", "de-CH")).toBe("05.01.2026");
  });

  it("writes Swiss French and Swiss Italian dates like Swiss German, long ones in words", () => {
    expect(formatDate("2026-01-05", "fr-CH")).toBe("05.01.2026");
    expect(formatDate("2026-01-05", "it-CH")).toBe("05.01.2026");
    expect(formatDate("2026-01-05", "fr-CH", "long")).toBe("5 janvier 2026");
    expect(formatDate("2026-01-05", "it-CH", "long")).toBe("5 gennaio 2026");
    expect(formatDateTime("2026-01-05T08:15:00Z", "fr-CH", "Europe/Zurich")).toBe(
      "05.01.2026 09:15",
    );
    expect(formatDateTime("2026-01-05T08:15:00Z", "it-CH", "Europe/Zurich")).toBe(
      "05.01.2026, 09:15",
    );
  });

  it("returns non-ISO input unchanged", () => {
    expect(formatDate("", "en", "long")).toBe("");
    expect(formatDate("05.01.2026", "de-CH")).toBe("05.01.2026");
  });

  it("uses British conventions for English", () => {
    expect(formatDate("2026-01-05", "en", "long")).toBe("5 January 2026");
  });

  it("formats date-times in an explicit time zone", () => {
    expect(formatDateTime("2026-01-05T08:15:00Z", "de-CH", "Europe/Zurich")).toBe(
      "05.01.2026, 09:15",
    );
    expect(formatDateTime("2026-01-05T08:15:00Z", "de-CH")).toMatch(/^05\.01\.2026, \d\d:\d\d$/);
  });
});

describe("formatRelative", () => {
  const now = new Date("2026-01-05T12:00:00Z");
  it.each([
    [-2_000, "de-DE", "vor 2 Sekunden"],
    [0, "de-DE", "jetzt"],
    [-90_000, "de-DE", "vor 1 Minute"],
    [-2 * 3600_000, "en", "2 hours ago"],
    [-24 * 3600_000, "en", "yesterday"],
    [-40 * 24 * 3600_000, "en", "last month"],
    [-400 * 24 * 3600_000, "en", "last year"],
    [3 * 3600_000, "en", "in 3 hours"],
    [-2_000, "fr-CH", "il y a 2 secondes"],
    [-24 * 3600_000, "it-CH", "ieri"],
  ] as const)("%d ms in %s", (offset, locale, expected) => {
    expect(formatRelative(new Date(now.getTime() + offset), now, locale)).toBe(expected);
  });
});

describe("formatMonth", () => {
  it.each([
    ["de-CH", "2026-01-01", "Jan. 26"],
    ["de-AT", "2026-01-01", "Jän. 26"],
    ["en", "2026-03-01", "Mar 26"],
    ["fr-CH", "2026-01-01", "janv. 26"],
    ["it-CH", "2026-01-01", "gen 26"],
  ] as const)("%s %s", (locale, date, expected) => {
    expect(plain(formatMonth(date, locale))).toBe(expected);
  });

  it("returns other input unchanged", () => {
    expect(formatMonth("März", "de-CH")).toBe("März");
  });
});

describe("formatBytes", () => {
  it.each([
    [0, "de-CH", "0 Byte"],
    [999, "de-CH", "999 Byte"],
    [48_000, "de-CH", "48 kB"],
    [999_950, "de-CH", "1 MB"],
    [950, "en", "950 byte"],
    [1_250_000, "de-DE", "1,3 MB"],
    [2_000_000_000, "en", "2 GB"],
    [48_000, "fr-CH", "48 ko"],
  ] as const)("formats %d bytes in %s", (bytes, locale, expected) => {
    expect(plain(formatBytes(bytes, locale))).toBe(expected);
  });
});

describe("formatChange", () => {
  it("shows the direction with a sign and rounds to whole percent", () => {
    expect(formatChange(0.12, "de-CH")).toBe("+12%");
    expect(formatChange(-0.07, "de-CH")).toBe("-7%");
    expect(formatChange(-0.003, "de-CH")).toBe("0%");
    expect(formatChange(0, "en")).toBe("0%");
    expect(formatChange(1.5, "en")).toBe("+150%");
  });
});
