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
import { translatorFor } from "@/lib/i18n";
import { isLocale, isMachineTranslated, LOCALE_NAMES, SUPPORTED_LOCALES } from "@/lib/locale";

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
          {SUPPORTED_LOCALES.map((option) => {
            // Machine translated languages say so in their own language, as their name does.
            const noteId = `language-note-${option}`;
            const note = isMachineTranslated(option);
            return (
              <DropdownMenuRadioItem
                key={option}
                value={option}
                lang={option}
                aria-describedby={note ? noteId : undefined}
              >
                <span className="flex flex-col">
                  {LOCALE_NAMES[option]}
                  {note ? (
                    <span id={noteId} aria-hidden="true" className="text-xs text-muted-foreground">
                      {translatorFor(option)("language.machineTranslated")}
                    </span>
                  ) : null}
                </span>
              </DropdownMenuRadioItem>
            );
          })}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
