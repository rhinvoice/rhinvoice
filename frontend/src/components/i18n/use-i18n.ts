import { useContext } from "react";

import { I18nContext, type I18nValue } from "@/components/i18n/i18n-context";

export function useI18n(): I18nValue {
  return useContext(I18nContext);
}
