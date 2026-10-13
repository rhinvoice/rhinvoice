import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

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
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import type { DocumentDetail, WriteOffInput } from "@/features/documents/api";
import {
  endOfInvoiceYear,
  isWriteOffDate,
  WRITE_OFF_REASONS,
} from "@/features/documents/write-off-model";
import { FormAlert } from "@/features/shared/form-alert";
import { fields } from "@/features/shared/form-schema";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { todayIso } from "@/lib/dates";
import { formatMoney } from "@/lib/format";

interface WriteOffDialogProps {
  readonly document: DocumentDetail;
  /** What the write-off means for the tax in the company's country, with its legal basis. */
  readonly hint: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onSubmit: (writeOff: WriteOffInput) => Promise<unknown>;
}

/** Give up collecting the open rest of an invoice: date, reason and what it means. */
export function WriteOffDialog({
  document,
  hint,
  open,
  onOpenChange,
  onSubmit,
}: WriteOffDialogProps) {
  const { t } = useI18n();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("writeOff.title", { number: document.number ?? "" })}</DialogTitle>
          <DialogDescription>{t("writeOff.description")}</DialogDescription>
        </DialogHeader>
        {/* Mounted per opening, so the form starts with fresh defaults. */}
        <WriteOffForm
          document={document}
          hint={hint}
          onCancel={() => {
            onOpenChange(false);
          }}
          onSubmit={async (writeOff) => {
            await onSubmit(writeOff);
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

interface WriteOffFormProps {
  readonly document: DocumentDetail;
  readonly hint: string;
  readonly onCancel: () => void;
  readonly onSubmit: (writeOff: WriteOffInput) => Promise<void>;
}

function WriteOffForm({ document, hint, onCancel, onSubmit }: WriteOffFormProps) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const today = todayIso();
  const issueDate = document.issue_date;
  const schema = useMemo(() => {
    const f = fields(t, locale);
    return z.object({
      written_off_on: z
        .string()
        .refine((value) => isWriteOffDate(value, issueDate, today), t("writeOff.dateRange")),
      reason: z.enum(WRITE_OFF_REASONS),
      note: f.optionalText(500),
    });
  }, [t, locale, issueDate, today]);
  const form = useForm({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: { written_off_on: today, reason: "gone" as const, note: "" },
  });
  const { errors, isSubmitting } = form.formState;
  const setDate = (value: string) => {
    form.setValue("written_off_on", value, { shouldValidate: true, shouldDirty: true });
  };

  const submit = form.handleSubmit(async (values) => {
    try {
      await onSubmit({
        writtenOffOn: values.written_off_on,
        reason: values.reason,
        note: values.note,
      });
    } catch (caught) {
      form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
    }
  });

  return (
    <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)} noValidate>
      <FormAlert message={errors.root?.message ?? null} />
      <dl className="flex justify-between gap-4 text-sm">
        <dt className="text-muted-foreground">{t("writeOff.openAmount")}</dt>
        <dd className="font-semibold tabular-nums">
          {formatMoney(document.open_amount, document.currency, locale)}
        </dd>
      </dl>
      <div className="flex flex-col gap-2">
        <Field label={t("writeOff.date")} error={errors.written_off_on?.message}>
          <Input
            id="write-off-date"
            type="date"
            min={issueDate ?? undefined}
            max={today}
            {...form.register("written_off_on")}
          />
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              setDate(today);
            }}
          >
            {t("writeOff.today")}
          </Button>
          {issueDate === null ? null : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setDate(endOfInvoiceYear(issueDate, today));
              }}
            >
              {t("writeOff.endOfInvoiceYear")}
            </Button>
          )}
        </div>
      </div>
      <Field label={t("writeOff.reason")} error={errors.reason?.message}>
        <NativeSelect id="write-off-reason" {...form.register("reason")}>
          {WRITE_OFF_REASONS.map((reason) => (
            <option key={reason} value={reason}>
              {t(`writeOff.reason.${reason}`)}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field
        label={t("writeOff.note")}
        error={errors.note?.message}
        optionalLabel={t("common.optional")}
      >
        <Input id="write-off-note" {...form.register("note")} />
      </Field>
      <p className="text-sm text-muted-foreground">{hint}</p>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {t("writeOff.submit")}
        </Button>
      </DialogFooter>
    </form>
  );
}

interface RemoveWriteOffDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onConfirm: () => void;
}

/** Taking a write-off back reopens the invoice; asked first, as it is noted in the history. */
export function RemoveWriteOffDialog({ open, onOpenChange, onConfirm }: RemoveWriteOffDialogProps) {
  const { t } = useI18n();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("writeOff.removeTitle")}</AlertDialogTitle>
          <AlertDialogDescription>{t("writeOff.removeDescription")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>{t("writeOff.remove")}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
