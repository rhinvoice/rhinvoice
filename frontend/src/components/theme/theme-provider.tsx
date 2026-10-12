import { useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";

import { ThemeContext } from "@/components/theme/theme-context";
import { readStorage, writeStorage } from "@/lib/storage";
import {
  applyTheme,
  isThemePreference,
  resolveTheme,
  THEME_STORAGE_KEY,
  type ThemePreference,
} from "@/lib/theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function subscribe(callback: () => void): () => void {
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", callback);
  return () => {
    query.removeEventListener("change", callback);
  };
}

function systemPrefersDark(): boolean {
  return window.matchMedia(DARK_QUERY).matches;
}

function initialPreference(): ThemePreference {
  const stored = readStorage(THEME_STORAGE_KEY);
  return isThemePreference(stored) ? stored : "system";
}

/** Light, dark or system theme; public/theme-init.js applies it before the first paint. */
export function ThemeProvider({ children }: { readonly children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(initialPreference);
  const prefersDark = useSyncExternalStore(subscribe, systemPrefersDark);
  const theme = resolveTheme(preference, prefersDark);

  useEffect(() => {
    applyTheme(document.documentElement, theme);
  }, [theme]);

  const value = useMemo(
    () => ({
      preference,
      theme,
      setPreference: (next: ThemePreference) => {
        writeStorage(THEME_STORAGE_KEY, next);
        setPreferenceState(next);
      },
    }),
    [preference, theme],
  );
  return <ThemeContext value={value}>{children}</ThemeContext>;
}
