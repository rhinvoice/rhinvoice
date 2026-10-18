import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { LandmarkIcon, PencilIcon, PlusIcon, StarIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  bankAccountsQuery,
  useDeleteBankAccount,
  useSaveBankAccount,
  type BankAccount,
} from "@/features/company/api";
import {
  bankAccountSchema,
  bankAccountToForm,
  emptyBankAccount,
  formToRequest,
  type BankAccountFormValues,
} from "@/features/company/bank-account-form-model";
import { FormAlert } from "@/features/shared/form-alert";
import { applyServerErrors } from "@/features/shared/server-errors";
import { offersQrIban, type CountryProfile } from "@/features/shared/country-profile-model";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { formatIban } from "@/lib/validation/iban";
import { useUnsavedChanges } from "@/features/shared/use-unsaved-changes";

type Editing = { readonly account: BankAccount | null } | null;

export function BankAccountsSettings({
  defaultHolder,
  defaultCurrency,
  profile,
}: {
  readonly defaultHolder: string;
  readonly defaultCurrency: "CHF" | "EUR";
  /** The company's country profile: the QR-IBAN belongs to the Swiss QR-bill. */
  readonly profile: CountryProfile | undefined;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const accounts = useQuery(bankAccountsQuery);
  const remove = useDeleteBankAccount();
  const [editing, setEditing] = useState<Editing>(null);
  const [deleting, setDeleting] = useState<BankAccount | null>(null);

  const addButton = (
    <Button
      onClick={() => {
        setEditing({ account: null });
      }}
    >
      <PlusIcon aria-hidden="true" />
      {t("bank.add")}
    </Button>
  );

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">{t("bank.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("bank.description")}</p>
        </div>
        {accounts.data !== undefined && accounts.data.length > 0 ? addButton : null}
      </div>
      <FormAlert message={accounts.isError ? errorMessage(accounts.error) : null} />
      {accounts.data === undefined ? (
        accounts.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : null
      ) : accounts.data.length === 0 ? (
        <EmptyState
          icon={LandmarkIcon}
          title={t("bank.emptyTitle")}
          description={t("bank.emptyDescription")}
          action={addButton}
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {accounts.data.map((account) => (
            <li key={account.id}>
              <Card className="gap-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex flex-col gap-1">
                    <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                      {account.bank_name}
                      <Badge variant="info">{account.currency}</Badge>
                      {account.is_default ? (
                        <Badge variant="success">
                          <StarIcon aria-hidden="true" />
                          {t("common.default")}
                        </Badge>
                      ) : null}
                    </CardTitle>
                    <CardDescription>{account.holder}</CardDescription>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`${t("common.edit")}: ${account.bank_name} ${account.currency}`}
                      onClick={() => {
                        setEditing({ account });
                      }}
                    >
                      <PencilIcon aria-hidden="true" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`${t("common.delete")}: ${account.bank_name} ${account.currency}`}
                      onClick={() => {
                        setDeleting(account);
                      }}
                    >
                      <Trash2Icon aria-hidden="true" />
                    </Button>
                  </div>
                </div>
                <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[8rem_1fr]">
                  <dt className="text-muted-foreground">{t("bank.iban")}</dt>
                  <dd className="font-mono">{account.iban_formatted}</dd>
                  {account.qr_iban === null ? null : (
                    <>
                      <dt className="text-muted-foreground">{t("bank.qrIban")}</dt>
                      <dd className="font-mono">{formatIban(account.qr_iban)}</dd>
                    </>
                  )}
                  {account.bic === null ? null : (
                    <>
                      <dt className="text-muted-foreground">{t("bank.bic")}</dt>
                      <dd className="font-mono">{account.bic}</dd>
                    </>
                  )}
                </dl>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {editing === null ? null : (
        <BankAccountDialog
          account={editing.account}
          defaults={emptyBankAccount(defaultCurrency, defaultHolder)}
          profile={profile}
          onClose={() => {
            setEditing(null);
          }}
        />
      )}

      <AlertDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("bank.deleteTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("bank.deleteDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              destructive
              onClick={() => {
                if (deleting === null) return;
                remove.mutate(deleting.id, {
                  onSuccess: () => toast.success(t("bank.deleted")),
                  onError: (caught) => toast.error(errorMessage(caught)),
                });
              }}
            >
              {t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function BankAccountDialog({
  account,
  defaults,
  profile,
  onClose,
}: {
  readonly account: BankAccount | null;
  readonly defaults: BankAccountFormValues;
  readonly profile: CountryProfile | undefined;
  readonly onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveBankAccount(account?.id ?? null);
  const form = useForm<BankAccountFormValues>({
    resolver: zodResolver(bankAccountSchema(t, locale)),
    mode: "onTouched",
    defaultValues: account === null ? defaults : bankAccountToForm(account),
  });
  const { errors, isSubmitting, isDirty } = form.formState;
  useUnsavedChanges(isDirty);
  const error = (name: keyof BankAccountFormValues) => errors[name]?.message;
  const submit = form.handleSubmit(async (values) => {
    try {
      await save.mutateAsync(formToRequest(values));
      toast.success(t("bank.saved"));
      onClose();
    } catch (caught) {
      const attached = applyServerErrors(caught, form.setError, t, (field) =>
        field in defaults ? (field as keyof BankAccountFormValues) : null,
      );
      if (!attached) form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
    }
  });

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{account === null ? t("bank.add") : t("bank.edit")}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)} noValidate>
          <FormAlert message={errors.root?.message ?? null} />
          <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <Field label={t("bank.bankName")} error={error("bank_name")}>
              <Input id="bank_name" {...form.register("bank_name")} />
            </Field>
            <Field label={t("bank.currency")} error={error("currency")}>
              <NativeSelect id="currency" {...form.register("currency")}>
                <option value="CHF">CHF</option>
                <option value="EUR">EUR</option>
              </NativeSelect>
            </Field>
          </div>
          <Field label={t("bank.holder")} error={error("holder")}>
            <Input id="holder" {...form.register("holder")} />
          </Field>
          <Field label={t("bank.iban")} error={error("iban")}>
            <Input
              id="iban"
              className="font-mono uppercase"
              autoComplete="off"
              spellCheck={false}
              {...form.register("iban")}
            />
          </Field>
          {offersQrIban(profile, account !== null && account.qr_iban !== null) ? (
            <Field
              label={t("bank.qrIban")}
              description={t("bank.qrIbanHint")}
              error={error("qr_iban")}
              optionalLabel={t("common.optional")}
            >
              <Input
                id="qr_iban"
                className="font-mono uppercase"
                autoComplete="off"
                spellCheck={false}
                {...form.register("qr_iban")}
              />
            </Field>
          ) : null}
          <Field label={t("bank.bic")} error={error("bic")} optionalLabel={t("common.optional")}>
            <Input
              id="bic"
              className="font-mono uppercase"
              autoComplete="off"
              spellCheck={false}
              {...form.register("bic")}
            />
          </Field>
          <Controller
            control={form.control}
            name="is_default"
            render={({ field }) => (
              <div className="flex items-center justify-between gap-4">
                <Label htmlFor="is_default">{t("bank.isDefault")}</Label>
                <Switch id="is_default" checked={field.value} onCheckedChange={field.onChange} />
              </div>
            )}
          />
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
