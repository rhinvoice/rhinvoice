import { useQuery } from "@tanstack/react-query";
import { useState, type SyntheticEvent } from "react";

import { useRunOnce } from "@/components/use-run-once";
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
import { previewQuery, type DocumentDetail } from "@/features/documents/api";
import { conversionRequest, initialChoice } from "@/features/documents/convert-model";
import { inTotalTag } from "@/features/documents/in-total-model";
import { TotalTag } from "@/features/documents/line-items";
import { FormAlert } from "@/features/shared/form-alert";
import { taxChoiceOf } from "@/features/shared/tax-rate-model";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { cn } from "@/lib/cn";
import { todayIso } from "@/lib/dates";
import { formatMoney } from "@/lib/format";

interface ConvertDialogProps {
  readonly quote: DocumentDetail;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** Creates the invoice of the chosen items (ids of the quote's lines). */
  readonly onConvert: (lineIds: readonly string[]) => Promise<unknown>;
}

/**
 * Which items of a quote with options the customer took (variant 3B, ADR 0045): every item
 * with a checkbox, those in the total ticked, and the invoice's total of the choice.
 */
export function ConvertDialog({ quote, open, onOpenChange, onConvert }: ConvertDialogProps) {
  const { t } = useI18n();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("documents.convertTitle")}</DialogTitle>
          <DialogDescription>{t("documents.convertDescription")}</DialogDescription>
        </DialogHeader>
        {/* Mounted per opening, so the choice starts with the items in the total. */}
        <ConvertForm
          quote={quote}
          onCancel={() => {
            onOpenChange(false);
          }}
          onConvert={onConvert}
        />
      </DialogContent>
    </Dialog>
  );
}

interface ConvertFormProps {
  readonly quote: DocumentDetail;
  readonly onCancel: () => void;
  readonly onConvert: (lineIds: readonly string[]) => Promise<unknown>;
}

function ConvertForm({ quote, onCancel, onConvert }: ConvertFormProps) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const [chosen, setChosen] = useState(() => new Set(initialChoice(quote.lines)));
  const [failure, setFailure] = useState<string | null>(null);
  const once = useRunOnce();
  const preview = useQuery(
    previewQuery(chosen.size === 0 ? null : conversionRequest(quote, chosen, locale, todayIso())),
  );
  const marked = quote.lines.map((line) => ({ ...line, key: line.id, tax: taxChoiceOf(line) }));
  const money = (amount: string) => formatMoney(amount, quote.currency, locale);

  const toggle = (id: string, on: boolean) => {
    setChosen((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  };
  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (chosen.size === 0) return;
    void once.run(async () => {
      try {
        await onConvert([...chosen]);
        once.finish();
      } catch (caught) {
        setFailure(errorMessage(caught) ?? t("error.generic"));
      }
    });
  };

  return (
    <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
      <FormAlert message={failure} />
      <fieldset className="flex flex-col gap-2">
        <legend className="sr-only">{t("documents.convertPositions")}</legend>
        {quote.lines.map((line, index) =>
          line.kind === "item" ? (
            <label
              key={line.id}
              className={cn(
                "grid cursor-pointer grid-cols-[1rem_minmax(0,1fr)_auto] items-center gap-3 rounded-lg border px-3 py-2 text-sm transition-colors hover:bg-muted",
                !chosen.has(line.id) && "text-muted-foreground",
              )}
            >
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={chosen.has(line.id)}
                onChange={(event) => {
                  toggle(line.id, event.target.checked);
                }}
              />
              <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                <span className="min-w-0 break-words">{line.description}</span>
                <TotalTag tag={inTotalTag(marked, index)} />
              </span>
              <span className="tabular-nums">{line.amount === null ? "" : money(line.amount)}</span>
            </label>
          ) : null,
        )}
      </fieldset>
      {chosen.size === 0 ? (
        <p className="text-sm text-destructive">{t("error.no_positions_chosen")}</p>
      ) : null}
      {/* The total first; the buttons follow below it where the row is too narrow. */}
      <DialogFooter className="flex-col items-center gap-y-3 sm:flex-row sm:flex-wrap sm:justify-between">
        <p className="font-semibold whitespace-nowrap tabular-nums" aria-live="polite">
          {chosen.size === 0 || preview.data === undefined
            ? null
            : t("documents.convertTotal", { amount: money(preview.data.totals.total) })}
        </p>
        <div className="flex flex-col-reverse gap-2 sm:ml-auto sm:flex-row">
          <Button type="button" variant="outline" onClick={onCancel}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" busy={once.busy} disabled={chosen.size === 0}>
            {t("documents.convertSubmit")}
          </Button>
        </div>
      </DialogFooter>
    </form>
  );
}
