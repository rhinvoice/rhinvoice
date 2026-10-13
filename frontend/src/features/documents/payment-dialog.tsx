import { zodResolver } from "@hookform/resolvers/zod";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useI18n } from "@/components/i18n/use-i18n";
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
import type { DocumentDetail, PaymentInput } from "@/features/documents/api";
import { paymentLimit } from "@/features/documents/write-off-model";
import { FormAlert } from "@/features/shared/form-alert";
import { fields, toApiDecimal } from "@/features/shared/form-schema";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { todayIso } from "@/lib/dates";
import { compareDecimal } from "@/lib/decimal";
import { formatDecimalInput, formatMoney } from "@/lib/format";

interface PaymentDialogProps {
  readonly document: DocumentDetail;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onSubmit: (payment: PaymentInput) => Promise<unknown>;
}

/** Record a (partial) payment: date = today and amount = open amount are prefilled. */
export function PaymentDialog({ document, open, onOpenChange, onSubmit }: PaymentDialogProps) {
  const { t, locale } = useI18n();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("documents.addPayment")}</DialogTitle>
          <DialogDescription>
            {t(
              document.status === "written_off"
                ? "writeOff.paymentDescription"
                : "documents.addPaymentDescription",
              { amount: formatMoney(paymentLimit(document), document.currency, locale) },
            )}
          </DialogDescription>
        </DialogHeader>
        {/* Mounted per opening, so the form starts with fresh defaults. */}
        <PaymentForm
          document={document}
          onCancel={() => {
            onOpenChange(false);
          }}
          onSubmit={async (payment) => {
            await onSubmit(payment);
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

interface PaymentFormProps {
  readonly document: DocumentDetail;
  readonly onCancel: () => void;
  readonly onSubmit: (payment: PaymentInput) => Promise<void>;
}

function PaymentForm({ document, onCancel, onSubmit }: PaymentFormProps) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  // A written-off invoice takes payments up to what was written off.
  const limit = paymentLimit(document);
  const schema = useMemo(() => {
    const f = fields(t, locale);
    return z
      .object({
        paid_on: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, t("validation.required")),
        amount: f.decimal({ max: 9_999_999_999.99, decimals: 2, required: true }),
        note: f.optionalText(500),
      })
      .superRefine((values, context) => {
        // Canonical decimal ("0" for empty input, which the field reports itself).
        const amount = toApiDecimal(values.amount, locale);
        if (values.amount !== "" && compareDecimal(amount, "0") <= 0) {
          context.addIssue({ code: "custom", path: ["amount"], message: t("validation.number") });
        } else if (compareDecimal(amount, limit) > 0) {
          context.addIssue({
            code: "custom",
            path: ["amount"],
            message: t("documents.paymentTooHigh", {
              amount: formatMoney(limit, document.currency, locale),
            }),
          });
        }
      });
  }, [t, locale, limit, document.currency]);
  const form = useForm({
    resolver: zodResolver(schema),
    mode: "onTouched",
    defaultValues: {
      paid_on: todayIso(),
      amount: formatDecimalInput(limit, locale, 2, 2),
      note: "",
    },
  });
  const { errors, isSubmitting } = form.formState;

  const submit = form.handleSubmit(async (values) => {
    try {
      await onSubmit({
        paidOn: values.paid_on,
        amount: toApiDecimal(values.amount, locale),
        note: values.note,
      });
    } catch (caught) {
      form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
    }
  });

  return (
    <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)} noValidate>
      <FormAlert message={errors.root?.message ?? null} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("documents.paidOn")} error={errors.paid_on?.message}>
          <Input id="payment-paid_on" type="date" {...form.register("paid_on")} />
        </Field>
        <Field
          label={t("documents.paymentAmount", { currency: document.currency })}
          error={errors.amount?.message}
        >
          <Input
            id="payment-amount"
            inputMode="decimal"
            className="text-right tabular-nums"
            {...form.register("amount")}
          />
        </Field>
      </div>
      <Field
        label={t("documents.paymentNote")}
        error={errors.note?.message}
        optionalLabel={t("common.optional")}
      >
        <Input id="payment-note" {...form.register("note")} />
      </Field>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {t("documents.recordPayment")}
        </Button>
      </DialogFooter>
    </form>
  );
}
