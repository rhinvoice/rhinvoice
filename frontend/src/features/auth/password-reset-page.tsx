import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CheckCircle2Icon, FileTextIcon } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CopyLine } from "@/components/copy-line";
import { useI18n } from "@/components/i18n/use-i18n";
import { Button, buttonVariants } from "@/components/ui/button";
import { ErrorSummary } from "@/components/ui/error-summary";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useDocumentTitle } from "@/components/use-document-title";
import { passwordResetQuery, useConfirmReset, useRequestResetCode } from "@/features/auth/api";
import { AuthLayout } from "@/features/auth/auth-layout";
import { FormAlert } from "@/features/shared/form-alert";
import { summaryItems } from "@/features/shared/form-errors";
import { useErrorMessage } from "@/features/shared/use-error-message";
import type { T } from "@/lib/i18n";

const MIN_PASSWORD_LENGTH = 12;

function resetSchema(t: T) {
  return z.object({
    email: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .pipe(z.email(t("validation.email"))),
    code: z.string().trim().min(1, t("validation.required")),
    new_password: z.string().min(MIN_PASSWORD_LENGTH, t("validation.passwordLength")),
  });
}

type ResetValues = z.infer<ReturnType<typeof resetSchema>>;

function BackToLogin({ primary = false }: { readonly primary?: boolean }) {
  const { t } = useI18n();
  return (
    <Link
      to="/login"
      search={{ redirect: "/" }}
      className={
        primary ? buttonVariants() : "inline-flex min-h-6 items-center self-center text-sm"
      }
    >
      {primary ? t("auth.reset.toLogin") : t("auth.reset.back")}
    </Link>
  );
}

/** On a server: the administrator sets the password with the command line. */
function ByAdministrator() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-4 text-sm">
      <p>{t("auth.reset.administrator")}</p>
      <CopyLine text="docker compose exec app rhinvoice user reset-password --email name@example.com" />
      <p>{t("auth.reset.whichAddress")}</p>
      <CopyLine text="docker compose exec app rhinvoice user list" />
      <BackToLogin />
    </div>
  );
}

/** Without Docker: a one-time code in the data folder on this computer. */
function ByFile({ location }: { readonly location: string }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const request = useRequestResetCode();
  const confirm = useConfirmReset();
  const [requested, setRequested] = useState(false);
  const form = useForm<ResetValues>({
    resolver: zodResolver(resetSchema(t)),
    mode: "onTouched",
    // The error summary takes the focus instead of the first invalid field.
    shouldFocusError: false,
    defaultValues: { email: "", code: "", new_password: "" },
  });
  const { errors, isSubmitted, submitCount } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    await confirm.mutateAsync(values).then(
      () => undefined,
      () => undefined,
    );
  });

  if (confirm.isSuccess) {
    return (
      <div className="flex flex-col gap-4">
        <p role="status" className="flex items-start gap-2 text-sm">
          <CheckCircle2Icon className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
          {t("auth.reset.done")}
        </p>
        <BackToLogin primary />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm">{t("auth.reset.file")}</p>
      <FormAlert message={errorMessage(request.error)} />
      <Button
        type="button"
        variant={requested ? "outline" : "default"}
        disabled={request.isPending}
        onClick={() => {
          request.mutate(undefined, {
            onSuccess: () => {
              setRequested(true);
            },
          });
        }}
      >
        {requested ? t("auth.reset.again") : t("auth.reset.request")}
      </Button>
      {requested ? (
        <>
          <div
            role="status"
            className="flex flex-col gap-1 rounded-lg border border-border bg-muted/50 p-3 text-sm"
          >
            <p className="flex items-start gap-2">
              <FileTextIcon
                className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              {t("auth.reset.opened")}
            </p>
            <code className="font-mono text-xs break-all">{location}</code>
          </div>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => void onSubmit(event)}
            noValidate
          >
            {isSubmitted ? (
              <ErrorSummary
                title={t("validation.summary", { count: Object.keys(errors).length })}
                submitCount={submitCount}
                items={summaryItems(errors, ["email", "code", "new_password"])}
              />
            ) : null}
            <FormAlert message={errorMessage(confirm.error)} />
            <Field label={t("auth.email")} error={errors.email?.message}>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                inputMode="email"
                {...form.register("email")}
              />
            </Field>
            <Field label={t("auth.reset.code")} error={errors.code?.message}>
              <Input
                id="code"
                autoComplete="one-time-code"
                autoCapitalize="characters"
                spellCheck={false}
                className="font-mono"
                {...form.register("code")}
              />
            </Field>
            <Field
              label={t("auth.reset.newPassword")}
              description={t("auth.passwordHint")}
              error={errors.new_password?.message}
            >
              <Input
                id="new_password"
                type="password"
                autoComplete="new-password"
                {...form.register("new_password")}
              />
            </Field>
            <Button type="submit" disabled={confirm.isPending}>
              {t("auth.reset.save")}
            </Button>
          </form>
        </>
      ) : null}
      <BackToLogin />
    </div>
  );
}

export function PasswordResetPage() {
  const { t } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("auth.reset.title") }));
  const info = useQuery(passwordResetQuery).data;
  return (
    <AuthLayout title={t("auth.reset.title")} description={t("auth.reset.description")}>
      {info === undefined ? null : info.method === "file" && info.location !== null ? (
        <ByFile location={info.location} />
      ) : (
        <ByAdministrator />
      )}
    </AuthLayout>
  );
}
