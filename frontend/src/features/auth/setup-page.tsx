import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { ErrorSummary } from "@/components/ui/error-summary";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useDocumentTitle } from "@/components/use-document-title";
import { useSetup } from "@/features/auth/api";
import { AuthLayout } from "@/features/auth/auth-layout";
import { FormAlert } from "@/features/shared/form-alert";
import { summaryItems } from "@/features/shared/form-errors";
import { useErrorMessage } from "@/features/shared/use-error-message";
import type { T } from "@/lib/i18n";

const MIN_PASSWORD_LENGTH = 12;

function setupSchema(t: T) {
  return z.object({
    display_name: z.string().trim().min(1, t("validation.required")),
    email: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .pipe(z.email(t("validation.email"))),
    password: z.string().min(MIN_PASSWORD_LENGTH, t("validation.passwordLength")),
  });
}

type SetupValues = z.infer<ReturnType<typeof setupSchema>>;

export function SetupPage() {
  const { t } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("auth.setupTitle") }));
  const navigate = useNavigate();
  const setup = useSetup();
  const errorMessage = useErrorMessage();
  const form = useForm<SetupValues>({
    resolver: zodResolver(setupSchema(t)),
    mode: "onTouched",
    // The error summary takes the focus instead of the first invalid field.
    shouldFocusError: false,
    defaultValues: { display_name: "", email: "", password: "" },
  });
  const { errors, isSubmitted, submitCount } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    await setup.mutateAsync(values).then(
      () => navigate({ to: "/" }),
      () => undefined,
    );
  });

  return (
    <AuthLayout title={t("auth.setupTitle")} description={t("auth.setupDescription")}>
      <form className="flex flex-col gap-4" onSubmit={(event) => void onSubmit(event)} noValidate>
        {isSubmitted ? (
          <ErrorSummary
            title={t("validation.summary", { count: Object.keys(errors).length })}
            submitCount={submitCount}
            items={summaryItems(errors, ["display_name", "email", "password"])}
          />
        ) : null}
        <FormAlert message={errorMessage(setup.error)} />
        <Field label={t("auth.displayName")} error={errors.display_name?.message}>
          <Input id="display_name" autoComplete="name" {...form.register("display_name")} />
        </Field>
        <Field label={t("auth.email")} error={errors.email?.message}>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            inputMode="email"
            {...form.register("email")}
          />
        </Field>
        <Field
          label={t("auth.newPassword")}
          description={t("auth.passwordHint")}
          error={errors.password?.message}
        >
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            {...form.register("password")}
          />
        </Field>
        <Button type="submit" disabled={setup.isPending}>
          {t("auth.setupSubmit")}
        </Button>
      </form>
    </AuthLayout>
  );
}
