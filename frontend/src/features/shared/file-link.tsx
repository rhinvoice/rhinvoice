import type { ReactNode } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { useSaveFile } from "@/features/shared/use-save-file";
import { inProgramWindow } from "@/lib/program-window";

/**
 * A link to a file of the API. It opens in a new tab; the program window saves the file
 * instead, because it hands new tabs to the default browser, where nobody is logged in.
 */
export function FileLink({
  href,
  className,
  children,
}: {
  readonly href: string;
  readonly className: string;
  readonly children: ReactNode;
}) {
  const { t } = useI18n();
  const save = useSaveFile();
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={className}
      onClick={(event) => {
        if (inProgramWindow(window)) {
          event.preventDefault();
          save(href);
        }
      }}
    >
      {children}
      {inProgramWindow(window) ? null : (
        <span className="sr-only">{t("common.opensInNewTab")}</span>
      )}
    </a>
  );
}
