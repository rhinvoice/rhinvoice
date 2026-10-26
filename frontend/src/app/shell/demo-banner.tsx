import { useQuery } from "@tanstack/react-query";
import { FlaskConicalIcon } from "lucide-react";

import { useI18n } from "@/components/i18n/use-i18n";
import { demoQuery } from "@/features/shared/demo-api";
import { websiteUrl } from "@/lib/about";
import { countryName } from "@/lib/countries";

/** A quiet strip on every page of a public demo: shared data, example accounts, reset hourly, no mail. */
export function DemoBanner() {
  const { t, locale } = useI18n();
  const demo = useQuery(demoQuery).data;
  if (demo?.enabled !== true) return null;
  return (
    <aside
      aria-label={t("demo.title")}
      className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 bg-accent px-4 py-1.5 text-center text-xs text-accent-foreground"
    >
      <span className="inline-flex items-center gap-1.5 font-medium">
        <FlaskConicalIcon className="size-3.5" aria-hidden="true" />
        {t("demo.title")}
      </span>
      <span>{t("demo.banner", { minutes: demo.reset_minutes ?? 60 })}</span>
      {demo.links.map((link) => (
        <a
          key={link.country}
          href={link.url}
          className="inline-flex min-h-6 items-center underline underline-offset-4"
        >
          {t("demo.countryDemo", { country: countryName(link.country, locale) })}
        </a>
      ))}
      <a
        href={websiteUrl(locale)}
        className="inline-flex min-h-6 items-center underline underline-offset-4"
      >
        rhinvoice.com
      </a>
    </aside>
  );
}
