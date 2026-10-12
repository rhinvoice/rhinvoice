import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldCheckIcon, ShieldIcon } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  useChangePassword,
  useTotpConfirm,
  useTotpDisable,
  useTotpSetup,
  type User,
} from "@/features/auth/api";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";

export function PasswordCard() {
  const { t } = useI18n();
  const change = useChangePassword();
  const errorMessage = useErrorMessage();
  const schema = z.object({
    current_password: z.string().min(1, t("validation.required")),
    new_password: z.string().min(12, t("validation.passwordLength")),
  });
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: { current_password: "", new_password: "" },
  });
  const onSubmit = form.handleSubmit(async (values) => {
    await change.mutateAsync(values).then(
      () => {
        form.reset();
        toast.success(t("settings.passwordChanged"));
      },
      () => undefined,
    );
  });
  const { errors } = form.formState;
  return (
    <Card aria-labelledby="password-title">
      <CardHeader>
        <CardTitle id="password-title">{t("settings.changePassword")}</CardTitle>
      </CardHeader>
      <form className="flex flex-col gap-4" onSubmit={(event) => void onSubmit(event)} noValidate>
        <FormAlert message={errorMessage(change.error)} />
        <Field label={t("settings.currentPassword")} error={errors.current_password?.message}>
          <Input
            id="current_password"
            type="password"
            autoComplete="current-password"
            {...form.register("current_password")}
          />
        </Field>
        <Field
          label={t("settings.newPassword")}
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
        <div>
          <Button type="submit" disabled={change.isPending}>
            {t("common.save")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

export function TotpCard({ user }: { readonly user: User }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const setup = useTotpSetup();
  const confirm = useTotpConfirm();
  const disable = useTotpDisable();
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [disabling, setDisabling] = useState(false);
  const Icon = user.totp_enabled ? ShieldCheckIcon : ShieldIcon;

  const onConfirm = () => {
    confirm.mutate(code.trim(), {
      onSuccess: () => {
        setCode("");
        setup.reset();
        toast.success(t("settings.totpActivated"));
      },
    });
  };
  const onDisable = () => {
    disable.mutate(
      { password, code: disableCode.trim() },
      {
        onSuccess: () => {
          setPassword("");
          setDisableCode("");
          setDisabling(false);
          toast.success(t("settings.totpDeactivated"));
        },
      },
    );
  };

  return (
    <Card aria-labelledby="totp-title">
      <CardHeader>
        <CardTitle id="totp-title" className="flex items-center gap-2">
          <Icon className="size-5" aria-hidden="true" />
          {t("settings.totpTitle")}
        </CardTitle>
        <CardDescription>
          {user.totp_enabled ? t("settings.totpEnabled") : t("settings.totpDisabled")} ·{" "}
          {t("settings.totpDescription")}
        </CardDescription>
      </CardHeader>
      <FormAlert message={errorMessage(setup.error ?? confirm.error ?? disable.error)} />
      {user.totp_enabled ? (
        disabling ? (
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              onDisable();
            }}
          >
            <Field label={t("auth.password")} description={t("settings.totpDisableConfirm")}>
              <Input
                id="totp_disable_password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
              />
            </Field>
            <Field label={t("auth.totpCode")} description={t("auth.totpHint")}>
              <Input
                id="totp_disable_code"
                autoComplete="one-time-code"
                inputMode="numeric"
                maxLength={6}
                value={disableCode}
                onChange={(event) => {
                  setDisableCode(event.target.value);
                }}
              />
            </Field>
            <div className="flex gap-2">
              <Button type="submit" variant="destructive" disabled={disable.isPending}>
                {t("settings.totpDisable")}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setDisabling(false);
                }}
              >
                {t("common.cancel")}
              </Button>
            </div>
          </form>
        ) : (
          <div>
            <Button
              variant="outline"
              onClick={() => {
                setDisabling(true);
              }}
            >
              {t("settings.totpDisable")}
            </Button>
          </div>
        )
      ) : setup.data === undefined ? (
        <div>
          <Button
            variant="outline"
            disabled={setup.isPending}
            onClick={() => {
              setup.mutate();
            }}
          >
            {t("settings.totpEnable")}
          </Button>
        </div>
      ) : (
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            onConfirm();
          }}
        >
          <p className="text-sm">{t("settings.totpScan")}</p>
          <Field label={t("settings.totpSecret")}>
            <Input id="totp_secret" readOnly value={setup.data.secret} className="font-mono" />
          </Field>
          <Field label={t("auth.totpCode")} description={t("auth.totpHint")}>
            <Input
              id="totp_code"
              autoComplete="one-time-code"
              inputMode="numeric"
              maxLength={6}
              value={code}
              onChange={(event) => {
                setCode(event.target.value);
              }}
            />
          </Field>
          <div>
            <Button type="submit" disabled={confirm.isPending}>
              {t("settings.totpConfirm")}
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
