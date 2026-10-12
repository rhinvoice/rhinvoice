import { useEffect, useMemo, useState, type ReactNode } from "react";

import { I18nContext } from "@/components/i18n/i18n-context";
import { translatorFor } from "@/lib/i18n";
import { isLocale, matchLocale, type Locale } from "@/lib/locale";
import { readStorage, writeStorage } from "@/lib/storage";

export const LOCALE_STORAGE_KEY = "rhinvoice.locale";

function initialLocale(): Locale {
  const stored = readStorage(LOCALE_STORAGE_KEY);
  return stored !== null && isLocale(stored) ? stored : matchLocale(navigator.language);
}

export function I18nProvider({ children }: { readonly children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale === "en" ? "en" : locale;
  }, [locale]);

  const value = useMemo(
    () => ({
      locale,
      t: translatorFor(locale),
      setLocale: (next: Locale) => {
        writeStorage(LOCALE_STORAGE_KEY, next);
        setLocaleState(next);
      },
    }),
    [locale],
  );
  return <I18nContext value={value}>{children}</I18nContext>;
}
