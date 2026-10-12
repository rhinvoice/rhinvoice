export const THEME_PREFERENCES = ["light", "dark", "system"] as const;
export type ThemePreference = (typeof THEME_PREFERENCES)[number];
export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "rhinvoice.theme";
export const DEFAULT_ACCENT_HUE = 250;

export function isThemePreference(value: unknown): value is ThemePreference {
  return typeof value === "string" && (THEME_PREFERENCES as readonly string[]).includes(value);
}

export function resolveTheme(preference: ThemePreference, systemPrefersDark: boolean): Theme {
  if (preference === "system") {
    return systemPrefersDark ? "dark" : "light";
  }
  return preference;
}

export function applyTheme(root: HTMLElement, theme: Theme): void {
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

/** Clamp and apply the configurable accent hue (0–360). */
export function applyAccentHue(root: HTMLElement, hue: number): void {
  const normalized = Number.isFinite(hue)
    ? ((Math.round(hue) % 360) + 360) % 360
    : DEFAULT_ACCENT_HUE;
  root.style.setProperty("--accent-hue", String(normalized));
}
