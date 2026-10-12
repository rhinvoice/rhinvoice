import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { ErrorSummary } from "@/components/ui/error-summary";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useDocumentTitle } from "@/components/use-document-title";
import { useLogin } from "@/features/auth/api";
import { AuthLayout } from "@/features/auth/auth-layout";
import { DemoCallout } from "@/features/auth/demo-callout";
import { demoQuery } from "@/features/shared/demo-api";
import { FormAlert } from "@/features/shared/form-alert";
import { summaryItems } from "@/features/shared/form-errors";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { ApiError } from "@/lib/api-error";
import type { T } from "@/lib/i18n";

function loginSchema(t: T, needsTotp: boolean) {
  return z.object({
    email: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .pipe(z.email(t("validation.email"))),
    password: z.string().min(1, t("validation.required")),
    totp_code: needsTotp
      ? z
          .string()
          .trim()
          .regex(/^\d{6}$/, t("validation.totp"))
      : z.string().optional(),
  });
}

type LoginValues = z.infer<ReturnType<typeof loginSchema>>;

export function LoginPage({ redirectTo }: { readonly redirectTo: string }) {
  const { t } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("auth.loginTitle") }));
  const navigate = useNavigate();
  const login = useLogin();
  const errorMessage = useErrorMessage();
  const [needsTotp, setNeedsTotp] = useState(false);
  const demo = useQuery(demoQuery).data;
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema(t, needsTotp)),
    mode: "onTouched",
    // The error summary takes the focus instead of the first invalid field.
    shouldFocusError: false,
    defaultValues: { email: "", password: "", totp_code: "" },
  });
  const { errors, isSubmitted, submitCount } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await login.mutateAsync({
        email: values.email,
        password: values.password,
        ...(needsTotp ? { totp_code: values.totp_code ?? "" } : {}),
      });
      await navigate({ to: redirectTo });
    } catch (error) {
      if (error instanceof ApiError && error.code === "totp_required") {
        setNeedsTotp(true);
      }
    }
  });

  const signInToDemo = async () => {
    const email = demo?.email ?? null;
    const password = demo?.password ?? null;
    if (email === null || password === null) return;
    try {
      await login.mutateAsync({ email, password });
      await navigate({ to: redirectTo });
    } catch {
      // The error is shown above the form like any failed login.
    }
  };

  const serverError =
    login.error instanceof ApiError && login.error.code === "totp_required"
      ? null
      : errorMessage(login.error);

  return (
    <AuthLayout
      title={t("auth.loginTitle")}
      description={t("auth.loginDescription")}
      aside={
        demo?.enabled === true ? (
          <DemoCallout demo={demo} pending={login.isPending} onSignIn={() => void signInToDemo()} />
        ) : null
      }
    >
      <form className="flex flex-col gap-4" onSubmit={(event) => void onSubmit(event)} noValidate>
        {isSubmitted ? (
          <ErrorSummary
            title={t("validation.summary", { count: Object.keys(errors).length })}
            submitCount={submitCount}
            items={summaryItems(errors, ["email", "password", "totp_code"])}
          />
        ) : null}
        <FormAlert message={serverError} />
        <Field label={t("auth.email")} error={errors.email?.message}>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            inputMode="email"
            {...form.register("email")}
          />
        </Field>
        <Field label={t("auth.password")} error={errors.password?.message}>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            {...form.register("password")}
          />
        </Field>
        {needsTotp ? (
          <Field
            label={t("auth.totpCode")}
            description={t("auth.totpHint")}
            error={errors.totp_code?.message}
          >
            <Input
              id="totp_code"
              autoComplete="one-time-code"
              inputMode="numeric"
              maxLength={6}
              autoFocus
              {...form.register("totp_code")}
            />
          </Field>
        ) : null}
        <Button type="submit" disabled={login.isPending}>
          {login.isPending ? t("auth.submitting") : t("auth.submit")}
        </Button>
      </form>
    </AuthLayout>
  );
}
