import { useRouter, type ErrorComponentProps } from "@tanstack/react-router";
import { TriangleAlertIcon } from "lucide-react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

/** Shown instead of a page that failed to render, with a way to try again. */
export function ErrorPage({ reset }: ErrorComponentProps) {
  const { t } = useI18n();
  const router = useRouter();
  return (
    <div role="alert">
      <EmptyState
        icon={TriangleAlertIcon}
        title={t("error.generic")}
        description={t("error.pageDescription")}
        action={
          <Button
            onClick={() => {
              reset();
              void router.invalidate();
            }}
          >
            {t("error.retry")}
          </Button>
        }
      />
    </div>
  );
}
