import { describe, expect, it } from "vitest";

import { addDays, daysBetween, monthWindow, todayIso, isoWeek } from "@/lib/dates";

describe("todayIso", () => {
  it("uses the local calendar date", () => {
    expect(todayIso(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05");
    expect(todayIso(new Date(2026, 11, 31, 0, 0))).toBe("2026-12-31");
  });

  it("defaults to now", () => {
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("daysBetween", () => {
  it.each([
    ["2026-01-01", "2026-01-01", 0],
    ["2026-01-01", "2026-01-13", 12],
    ["2026-03-28", "2026-03-30", 2], // across the daylight saving change
    ["2026-02-01", "2026-01-31", -1],
    ["2024-02-28", "2024-03-01", 2], // leap year
  ])("%s → %s", (from, to, expected) => {
    expect(daysBetween(from, to)).toBe(expected);
  });

  it("rejects other formats", () => {
    expect(() => daysBetween("5.1.2026", "2026-01-05")).toThrow("not an ISO date: 5.1.2026");
  });
});

describe("monthWindow", () => {
  it("lists the months up to today's month, oldest first", () => {
    expect(monthWindow("2026-03-09", 4)).toEqual([
      "2025-12-01",
      "2026-01-01",
      "2026-02-01",
      "2026-03-01",
    ]);
  });

  it("handles a single month and long windows", () => {
    expect(monthWindow("2026-12-31", 1)).toEqual(["2026-12-01"]);
    const year = monthWindow("2026-01-15", 12);
    expect(year[0]).toBe("2025-02-01");
    expect(year[11]).toBe("2026-01-01");
  });
});

describe("addDays", () => {
  it.each([
    ["2026-01-15", 30, "2026-02-14"],
    ["2026-03-28", 2, "2026-03-30"],
    ["2026-10-24", 10, "2026-11-03"],
    ["2024-02-28", 1, "2024-02-29"],
    ["2026-01-01", -1, "2025-12-31"],
    ["2026-05-05", 0, "2026-05-05"],
  ])("%s + %i days", (from, days, expected) => {
    expect(addDays(from, days)).toBe(expected);
  });
});

describe("isoWeek", () => {
  it.each([
    ["2026-01-01", 1],
    ["2026-03-09", 11],
    ["2026-10-12", 42],
    ["2026-12-31", 53],
    ["2027-01-03", 53],
    ["2027-01-04", 1],
    ["2025-12-29", 1],
    ["2024-12-30", 1],
  ])("%s is week %d", (date, week) => {
    expect(isoWeek(date)).toBe(week);
  });
});
