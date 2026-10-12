import { ExternalLinkIcon } from "lucide-react";
import type { ReactNode } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { cn } from "@/lib/cn";

/** A link that opens another site in a new tab and says so to screen readers. */
export function ExternalLink({
  href,
  className,
  icon = true,
  children,
}: {
  readonly href: string;
  readonly className?: string;
  readonly icon?: boolean;
  readonly children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <a
      href={href}
      className={cn("inline-flex items-center gap-1 underline-offset-4 hover:underline", className)}
      rel="noreferrer"
      target="_blank"
    >
      {children}
      {icon ? <ExternalLinkIcon className="size-3.5" aria-hidden="true" /> : null}
      <span className="sr-only">{t("common.opensInNewTab")}</span>
    </a>
  );
}
