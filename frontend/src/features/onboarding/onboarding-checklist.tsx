import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { CheckIcon } from "lucide-react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  onboardingQuery,
  useCheckNumbering,
  useDismissOnboarding,
  useShowOnboarding,
  type OnboardingStep,
} from "@/features/onboarding/api";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";

/** Setup steps of a new installation on the dashboard, until done or hidden. */
export function OnboardingChecklist() {
  const { t } = useI18n();
  const onboarding = useQuery(onboardingQuery).data;
  const errorMessage = useErrorMessage();
  const dismiss = useDismissOnboarding();
  const show = useShowOnboarding();
  if (onboarding === undefined || onboarding.dismissed || onboarding.complete) {
    return null;
  }
  const done = onboarding.steps.filter((step) => step.done).length;
  const total = onboarding.steps.length;
  return (
    <Card aria-labelledby="onboarding-title">
      <CardHeader>
        <CardTitle id="onboarding-title">{t("onboarding.title")}</CardTitle>
        <CardDescription>{t("onboarding.progress", { done, total })}</CardDescription>
        <progress
          className="h-2 w-full overflow-hidden rounded-full [&::-moz-progress-bar]:bg-primary [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-primary"
          max={total}
          value={done}
          aria-label={t("onboarding.progress", { done, total })}
        />
      </CardHeader>
      <ol className="flex flex-col divide-y divide-border/70">
        {onboarding.steps.map((step, index) => (
          <li key={step.key} className="flex flex-wrap items-center gap-3 py-3">
            <span
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-full border text-sm",
                step.done && "border-transparent bg-status-paid-bg text-status-paid-fg",
              )}
              aria-hidden="true"
            >
              {step.done ? <CheckIcon className="size-4" /> : index + 1}
            </span>
            <div className="flex min-w-0 flex-1 flex-col">
              <span className={cn("font-medium", step.done && "text-muted-foreground")}>
                {t(`onboarding.step.${step.key}`)}
                <span className="sr-only">
                  {" – "}
                  {step.done ? t("onboarding.done") : t("onboarding.open")}
                </span>
              </span>
              {step.done ? null : (
                <span className="text-sm text-muted-foreground">
                  {t(`onboarding.hint.${step.key}`)}
                </span>
              )}
            </div>
            {step.done ? null : <StepAction step={step.key} />}
          </li>
        ))}
      </ol>
      <div>
        <Button
          variant="ghost"
          size="sm"
          disabled={dismiss.isPending}
          onClick={() => {
            dismiss.mutate(undefined, {
              onSuccess: () =>
                toast.success(t("onboarding.dismissed"), {
                  action: {
                    label: t("common.undo"),
                    onClick: () => {
                      show.mutate();
                    },
                  },
                }),
              onError: (caught) => toast.error(errorMessage(caught) ?? t("error.generic")),
            });
          }}
        >
          {t("onboarding.dismiss")}
        </Button>
      </div>
    </Card>
  );
}

function StepAction({ step }: { readonly step: OnboardingStep }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const navigate = useNavigate();
  const checkNumbering = useCheckNumbering();
  switch (step) {
    case "company":
      return (
        <Button asChild variant="outline" size="sm">
          <Link to="/welcome">{t("onboarding.action.company")}</Link>
        </Button>
      );
    case "bank_account":
      return (
        <Button asChild variant="outline" size="sm">
          <Link to="/settings" search={{ tab: "bank-accounts" }}>
            {t("onboarding.action.bank_account")}
          </Link>
        </Button>
      );
    case "numbering":
      return (
        <Button
          variant="outline"
          size="sm"
          disabled={checkNumbering.isPending}
          onClick={() => {
            checkNumbering.mutate(undefined, {
              onSuccess: () => {
                void navigate({ to: "/settings", search: { tab: "numbering" } });
              },
              onError: (caught) => toast.error(errorMessage(caught) ?? t("error.generic")),
            });
          }}
        >
          {t("onboarding.action.numbering")}
        </Button>
      );
    case "customers":
      return (
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to="/customers/import">{t("onboarding.action.import")}</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link to="/customers/new">{t("onboarding.action.customers")}</Link>
          </Button>
        </div>
      );
    case "first_invoice":
      return (
        <Button asChild variant="outline" size="sm">
          <Link to="/invoices/new">{t("onboarding.action.first_invoice")}</Link>
        </Button>
      );
    case "backup":
      return (
        <Button asChild variant="outline" size="sm">
          <Link to="/settings" search={{ tab: "backup" }}>
            {t("onboarding.action.backup")}
          </Link>
        </Button>
      );
  }
}
