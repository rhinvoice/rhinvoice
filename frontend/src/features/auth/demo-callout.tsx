import { FlaskConicalIcon } from "lucide-react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import type { DemoInfo } from "@/features/shared/demo-api";
import { countryName } from "@/lib/countries";

/** The login of a public demo, so that visitors get in with one click. */
export function DemoCallout({
  demo,
  pending,
  onSignIn,
}: {
  readonly demo: DemoInfo;
  readonly pending: boolean;
  readonly onSignIn: () => void;
}) {
  const { t, locale } = useI18n();
  return (
    <section
      aria-labelledby="demo-title"
      className="flex flex-col gap-3 rounded-xl border border-primary/30 bg-accent p-4 text-sm text-accent-foreground"
    >
      {/* Above the page's h1, so a labelled region instead of a heading. */}
      <p id="demo-title" className="flex items-center gap-2 font-semibold">
        <FlaskConicalIcon className="size-4" aria-hidden="true" />
        {t("demo.title")}
      </p>
      <p>{t("demo.loginHint", { minutes: demo.reset_minutes ?? 60 })}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt>{t("auth.email")}</dt>
        <dd className="font-mono">{demo.email}</dd>
        <dt>{t("auth.password")}</dt>
        <dd className="font-mono">{demo.password}</dd>
      </dl>
      <Button type="button" onClick={onSignIn} disabled={pending}>
        {t("demo.signIn")}
      </Button>
      {demo.links.length > 0 ? (
        <p>
          {t("demo.otherCountries")}{" "}
          {demo.links.map((link, index) => (
            <span key={link.country}>
              {index > 0 ? " · " : null}
              <a href={link.url} className="font-medium underline underline-offset-4">
                {countryName(link.country, locale)}
              </a>
            </span>
          ))}
        </p>
      ) : null}
    </section>
  );
}
