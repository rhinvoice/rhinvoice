import { useQuery } from "@tanstack/react-query";
import { LibraryIcon, PlusIcon } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { taxRatesQuery, type TaxRate } from "@/features/tax-rates/api";
import { PresetDialog } from "@/features/tax-rates/preset-dialog";
import { TaxRateDialog } from "@/features/tax-rates/tax-rate-dialog";
import { rateSubline, todayPercent } from "@/features/tax-rates/tax-rate-form-model";
import { cn } from "@/lib/cn";
import { todayIso } from "@/lib/dates";

/** The edited rate by id (it stays current while hidden or shown), or a new one. */
type Editing = { readonly id: string | null } | null;

/** The company's tax rates as a table (ADR 0044, variant 1A); a click opens one. */
export function TaxRatesSettings() {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const rates = useQuery(taxRatesQuery);
  const [editing, setEditing] = useState<Editing>(null);
  const [presets, setPresets] = useState(false);
  const today = todayIso();
  const edited: TaxRate | null =
    editing?.id === null || editing === null
      ? null
      : (rates.data?.find((rate) => rate.id === editing.id) ?? null);

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">{t("taxRates.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("taxRates.description")}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => {
              setPresets(true);
            }}
          >
            <LibraryIcon aria-hidden="true" />
            {t("taxRates.fromPreset")}
          </Button>
          <Button
            onClick={() => {
              setEditing({ id: null });
            }}
          >
            <PlusIcon aria-hidden="true" />
            {t("taxRates.add")}
          </Button>
        </div>
      </div>
      <FormAlert message={rates.isError ? errorMessage(rates.error) : null} />
      {rates.data === undefined ? (
        rates.isPending ? (
          <Skeleton className="h-64 w-full" />
        ) : null
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("taxRates.name")}</TableHead>
              <TableHead>{t("taxRates.eInvoice")}</TableHead>
              <TableHead className="text-right">{t("taxRates.today")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rates.data.map((rate) => {
              const subline = rateSubline(rate, today, locale, t);
              return (
                <TableRow
                  key={rate.id}
                  // The name's button covers the row, so the whole row opens the rate.
                  // "relative" alone does not contain it in Apple's WebKit.
                  className={cn(
                    "relative [transform:translate(0)]",
                    rate.hidden && "text-muted-foreground",
                  )}
                >
                  <TableCell className="py-2">
                    <button
                      type="button"
                      className="inline-flex min-h-6 items-center text-left font-medium underline-offset-4 after:absolute after:inset-0 hover:underline"
                      onClick={() => {
                        setEditing({ id: rate.id });
                      }}
                    >
                      {rate.hidden ? t("taxRates.nameHidden", { name: rate.name }) : rate.name}
                    </button>
                    {subline === "" ? null : (
                      <span className="block text-xs text-muted-foreground">{subline}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="neutral" className="font-mono">
                      <span aria-hidden="true">{rate.category}</span>
                      <span className="sr-only">{t(`taxRates.category.${rate.category}`)}</span>
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right whitespace-nowrap tabular-nums">
                    {todayPercent(rate, today, locale)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      {editing === null || (editing.id !== null && edited === null) ? null : (
        <TaxRateDialog
          rate={edited}
          onClose={() => {
            setEditing(null);
          }}
        />
      )}
      {presets ? (
        <PresetDialog
          onClose={() => {
            setPresets(false);
          }}
        />
      ) : null}
    </div>
  );
}
