import { GlobeIcon } from "lucide-react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { isLocale, LOCALE_NAMES, SUPPORTED_LOCALES } from "@/lib/locale";

/** The language of the interface, kept per browser; documents keep their own language. */
export function LanguageToggle() {
  const { t, locale, setLocale } = useI18n();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={t("language.label")}>
          <GlobeIcon aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{t("language.label")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={locale}
          onValueChange={(value) => {
            if (isLocale(value)) setLocale(value);
          }}
        >
          {SUPPORTED_LOCALES.map((option) => (
            <DropdownMenuRadioItem
              key={option}
              value={option}
              lang={option === "en" ? "en" : option}
            >
              {LOCALE_NAMES[option]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
