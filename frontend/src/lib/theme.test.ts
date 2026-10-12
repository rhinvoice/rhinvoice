import { describe, expect, it } from "vitest";

import { applyAccentHue, applyTheme, isThemePreference, resolveTheme } from "@/lib/theme";

describe("theme", () => {
  it("validates preferences", () => {
    expect(isThemePreference("dark")).toBe(true);
    expect(isThemePreference("blue")).toBe(false);
    expect(isThemePreference(null)).toBe(false);
  });

  it("resolves the system preference", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("applies the theme class and colour scheme", () => {
    const root = document.createElement("html");
    applyTheme(root, "dark");
    expect(root.classList.contains("dark")).toBe(true);
    expect(root.style.colorScheme).toBe("dark");
    applyTheme(root, "light");
    expect(root.classList.contains("dark")).toBe(false);
    expect(root.style.colorScheme).toBe("light");
  });

  it.each([
    [200, "200"],
    [200.6, "201"],
    [360, "0"],
    [-30, "330"],
    [725, "5"],
    [Number.NaN, "250"],
    [Number.POSITIVE_INFINITY, "250"],
  ])("normalises accent hue %d to %s", (hue, expected) => {
    const root = document.createElement("html");
    applyAccentHue(root, hue);
    expect(root.style.getPropertyValue("--accent-hue")).toBe(expected);
  });
});
