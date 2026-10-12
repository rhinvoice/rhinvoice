import { createContext } from "react";

import type { Theme, ThemePreference } from "@/lib/theme";

export interface ThemeValue {
  readonly preference: ThemePreference;
  readonly theme: Theme;
  readonly setPreference: (preference: ThemePreference) => void;
}

export const ThemeContext = createContext<ThemeValue>({
  preference: "system",
  theme: "light",
  setPreference: () => undefined,
});
