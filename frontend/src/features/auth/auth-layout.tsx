import type { ReactNode } from "react";

import { ExternalLink } from "@/components/external-link";
import { LanguageToggle } from "@/components/i18n/language-toggle";
import { useI18n } from "@/components/i18n/use-i18n";
import { Card, CardDescription, CardHeader } from "@/components/ui/card";
import { APP_VERSION, MAKER, MAKER_URL, REPOSITORY_URL, websiteUrl } from "@/lib/about";

interface AuthLayoutProps {
  readonly title: string;
  readonly description: string;
  /** Shown above the card, e.g. the login of a public demo. */
  readonly aside?: ReactNode;
  readonly children: ReactNode;
}

export function AuthLayout({ title, description, aside, children }: AuthLayoutProps) {
  const { t, locale } = useI18n();
  return (
    <main id="main" className="relative flex min-h-dvh items-center justify-center px-4 py-12">
      <div className="absolute top-3 right-3">
        <LanguageToggle />
      </div>
      <div className="flex w-full max-w-sm flex-col gap-6">
        {/* The logo leads to rhinvoice.com: where the program comes from, also from the demo. */}
        <a
          href={websiteUrl(locale)}
          target="_blank"
          rel="noreferrer"
          aria-label={`Rhinvoice – rhinvoice.com${t("common.opensInNewTab")}`}
          className="flex items-center justify-center gap-2 self-center rounded-md text-foreground no-underline"
        >
          <img src="/favicon.svg" alt="" className="size-8" />
          <span className="text-lg font-semibold tracking-tight">Rhinvoice</span>
        </a>
        {aside}
        <Card>
          <CardHeader>
            <h1 className="text-lg leading-7 font-semibold">{title}</h1>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          {children}
        </Card>
        <p className="flex flex-wrap items-center justify-center gap-x-1.5 text-center text-xs text-muted-foreground">
          <span className="tabular-nums">
            Rhinvoice <span data-app-version>{APP_VERSION}</span>
          </span>
          <span aria-hidden="true">·</span>
          <ExternalLink href={REPOSITORY_URL} icon={false}>
            {t("about.openSource")}
          </ExternalLink>
          <span aria-hidden="true">·</span>
          <ExternalLink href={MAKER_URL} icon={false}>
            {t("about.madeBy", { maker: MAKER })}
          </ExternalLink>
        </p>
      </div>
    </main>
  );
}
