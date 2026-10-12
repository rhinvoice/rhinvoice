import { useContext } from "react";

import { ThemeContext, type ThemeValue } from "@/components/theme/theme-context";

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}
