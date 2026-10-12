import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider, LOCALE_STORAGE_KEY } from "@/components/i18n/i18n-provider";
import { useI18n } from "@/components/i18n/use-i18n";

const wrapper = ({ children }: { children: ReactNode }) => <I18nProvider>{children}</I18nProvider>;

describe("useI18n", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("derives the locale from the browser", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("de-AT");
    const { result } = renderHook(() => useI18n(), { wrapper });
    expect(result.current.locale).toBe("de-AT");
    expect(document.documentElement.lang).toBe("de-AT");
    expect(result.current.t("common.close")).toBe("Schließen");
  });

  it("prefers and stores an explicit locale", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    const { result } = renderHook(() => useI18n(), { wrapper });
    expect(result.current.locale).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    act(() => {
      result.current.setLocale("de-CH");
    });
    expect(result.current.t("common.close")).toBe("Schliessen");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("de-CH");
  });

  it("ignores unsupported stored locales", () => {
    vi.spyOn(navigator, "language", "get").mockReturnValue("en-US");
    localStorage.setItem(LOCALE_STORAGE_KEY, "fr-FR");
    expect(renderHook(() => useI18n(), { wrapper }).result.current.locale).toBe("en");
  });

  it("has a Swiss German default outside of the provider", () => {
    const { result } = renderHook(() => useI18n());
    expect(result.current.locale).toBe("de-CH");
    expect(() => {
      result.current.setLocale("en");
    }).not.toThrow();
  });
});
