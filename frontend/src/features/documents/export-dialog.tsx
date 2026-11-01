import { DownloadIcon } from "lucide-react";
import { useState, type SyntheticEvent } from "react";

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
import { NativeSelect } from "@/components/ui/native-select";
import { RadioCard } from "@/components/ui/radio-cards";
import {
  defaultChoice,
  EXPORT_FORMATS,
  exportUrl,
  fallbackName,
  MONTHS,
  PERIOD_KINDS,
  periodOf,
  periodProblem,
  QUARTERS,
  yearOptions,
  type ExportChoice,
} from "@/features/documents/export-model";
import { fetchFile, saveFile } from "@/features/documents/file-download";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { todayIso } from "@/lib/dates";
import { formatMonthName } from "@/lib/format";

interface ExportDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** Years with documents, to choose from besides the current one. */
  readonly years: readonly number[];
}

/** Download the issued invoices of a period for the bookkeeping: list, optionally with PDFs. */
export function ExportDialog({ open, onOpenChange, years }: ExportDialogProps) {
  const { t } = useI18n();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("export.title")}</DialogTitle>
          <DialogDescription>{t("export.description")}</DialogDescription>
        </DialogHeader>
        {/* Mounted per opening, so the dialog starts with the previous month again. */}
        <ExportForm
          years={years}
          onCancel={() => {
            onOpenChange(false);
          }}
          onDone={() => {
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

interface ExportFormProps {
  readonly years: readonly number[];
  readonly onCancel: () => void;
  readonly onDone: () => void;
}

function ExportForm({ years, onCancel, onDone }: ExportFormProps) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const today = todayIso();
  const [choice, setChoice] = useState<ExportChoice>(() => defaultChoice(today));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const change = (update: Partial<ExportChoice>) => {
    setChoice((current) => ({ ...current, ...update }));
  };
  const problem = periodProblem(choice);
  const period = periodOf(choice);
  const yearSelect = (
    <Field label={t("export.year")}>
      <NativeSelect
        id="export-year"
        value={String(choice.year)}
        onChange={(event) => {
          change({ year: Number(event.target.value) });
        }}
      >
        {yearOptions(today, years, choice.year).map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </NativeSelect>
    </Field>
  );

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    if (period === null) return;
    setBusy(true);
    setFailure(null);
    fetchFile(exportUrl(choice, period, locale), fallbackName(choice, period))
      .then(
        (file) => {
          saveFile(file);
          onDone();
        },
        (caught: unknown) => {
          setFailure(errorMessage(caught) ?? t("error.generic"));
        },
      )
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <form className="flex flex-col gap-5" onSubmit={submit} noValidate>
      <FormAlert message={failure} />
      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1.5 text-sm font-medium">{t("export.period")}</legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {PERIOD_KINDS.map((kind) => (
            <RadioCard
              key={kind}
              id={`export-period-${kind}`}
              name="export-period"
              value={kind}
              label={t(`export.period.${kind}`)}
              checked={choice.kind === kind}
              onChange={() => {
                change({ kind });
              }}
            />
          ))}
        </div>
      </fieldset>

      {choice.kind === "month" ? (
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("export.month")}>
            <NativeSelect
              id="export-month"
              value={String(choice.month)}
              onChange={(event) => {
                change({ month: Number(event.target.value) });
              }}
            >
              {MONTHS.map((month) => (
                <option key={month} value={month}>
                  {formatMonthName(month, locale)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {yearSelect}
        </div>
      ) : choice.kind === "quarter" ? (
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("export.quarter")}>
            <NativeSelect
              id="export-quarter"
              value={String(choice.quarter)}
              onChange={(event) => {
                change({ quarter: Number(event.target.value) });
              }}
            >
              {QUARTERS.map((quarter) => (
                <option key={quarter} value={quarter}>
                  {t("export.quarterName", { quarter })}
                </option>
              ))}
            </NativeSelect>
          </Field>
          {yearSelect}
        </div>
      ) : choice.kind === "year" ? (
        <div className="grid grid-cols-2 gap-3">{yearSelect}</div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("export.from")}>
            <Input
              id="export-from"
              type="date"
              value={choice.from}
              onChange={(event) => {
                change({ from: event.target.value });
              }}
            />
          </Field>
          <Field
            label={t("export.to")}
            error={problem === null ? undefined : t(`export.problem.${problem}`)}
          >
            <Input
              id="export-to"
              type="date"
              value={choice.to}
              onChange={(event) => {
                change({ to: event.target.value });
              }}
            />
          </Field>
        </div>
      )}

      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1.5 text-sm font-medium">{t("export.format")}</legend>
        <div className="grid grid-cols-3 gap-2">
          {EXPORT_FORMATS.map((format) => (
            <RadioCard
              key={format}
              id={`export-format-${format}`}
              name="export-format"
              value={format}
              label={t(`export.format.${format}`)}
              checked={choice.format === format}
              onChange={() => {
                change({ format });
              }}
            />
          ))}
        </div>
      </fieldset>

      <div className="flex flex-col gap-1">
        {/* The label is the target (WCAG 2.5.8), not the small box. */}
        <label className="flex min-h-6 cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={choice.withPdfs}
            className="mt-1 size-4 accent-primary"
            aria-describedby="export-pdfs-hint"
            onChange={(event) => {
              change({ withPdfs: event.target.checked });
            }}
          />
          <span className="text-sm font-medium">{t("export.withPdfs")}</span>
        </label>
        <p id="export-pdfs-hint" className="pl-7 text-sm text-muted-foreground">
          {t("export.withPdfsHint")}
        </p>
      </div>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={busy || period === null}>
          <DownloadIcon aria-hidden="true" />
          {busy ? t("export.preparing") : t("export.download")}
        </Button>
      </DialogFooter>
    </form>
  );
}
