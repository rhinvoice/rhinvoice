import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { demoQuery } from "@/features/shared/demo-api";

/**
 * What the public demo refuses (password, two-factor, logo, mail server) is not offered
 * there: a short note takes its place instead of a form that would only fail.
 */
export function NotInDemo({
  title,
  children,
}: {
  readonly title: string;
  readonly children: ReactNode;
}) {
  const { t } = useI18n();
  const demo = useQuery(demoQuery).data;
  if (demo?.enabled !== true) return children;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{t("demo.locked")}</CardDescription>
      </CardHeader>
    </Card>
  );
}
