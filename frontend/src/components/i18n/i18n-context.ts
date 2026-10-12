import { createContext } from "react";

import { translatorFor, type T } from "@/lib/i18n";
import { DEFAULT_LOCALE, type Locale } from "@/lib/locale";

export interface I18nValue {
  readonly locale: Locale;
  readonly t: T;
  readonly setLocale: (locale: Locale) => void;
}

export const I18nContext = createContext<I18nValue>({
  locale: DEFAULT_LOCALE,
  t: translatorFor(DEFAULT_LOCALE),
  setLocale: () => undefined,
});
