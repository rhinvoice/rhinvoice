import { act, render, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider } from "@/components/theme/theme-provider";
import { useTheme } from "@/components/theme/use-theme";
import { THEME_STORAGE_KEY } from "@/lib/theme";
import { installMatchMedia } from "@/test/match-media";

const wrapper = ({ children }: { children: ReactNode }) => (
  <ThemeProvider>{children}</ThemeProvider>
);

describe("useTheme", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "";
  });

  it("follows the system preference by default and reacts to changes", () => {
    const media = installMatchMedia(false);
    const { result, unmount } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.preference).toBe("system");
    expect(result.current.theme).toBe("light");
    act(() => {
      media.setDark(true);
    });
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    unmount();
    expect(media.listenerCount).toBe(0);
  });

  it("stores an explicit preference", () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => {
      result.current.setPreference("light");
    });
    expect(result.current.theme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("restores the stored preference and ignores invalid values", () => {
    installMatchMedia(false);
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    expect(renderHook(() => useTheme(), { wrapper }).result.current.theme).toBe("dark");
    localStorage.setItem(THEME_STORAGE_KEY, "purple");
    expect(renderHook(() => useTheme(), { wrapper }).result.current.preference).toBe("system");
  });

  it("has a harmless default outside of the provider", () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    expect(() => {
      result.current.setPreference("dark");
    }).not.toThrow();
  });

  it("renders children", () => {
    installMatchMedia(false);
    const { getByText } = render(<ThemeProvider>content</ThemeProvider>);
    expect(getByText("content")).toBeInTheDocument();
  });
});
