import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { ExternalLink } from "@/components/external-link";
import { useI18n } from "@/components/i18n/use-i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useRunOnce } from "@/components/use-run-once";
import { FormAlert } from "@/features/shared/form-alert";
import { percentOn } from "@/features/shared/tax-rate-model";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { taxRatePresetsQuery, useTakeOverPreset } from "@/features/tax-rates/api";
import { sourceLink } from "@/features/tax-rates/tax-rate-form-model";
import { todayIso } from "@/lib/dates";
import { formatPercent } from "@/lib/format";

/** The presets of the company's country not taken over yet, e.g. § 24 UStG (ADR 0044). */
export function PresetDialog({ onClose }: { readonly onClose: () => void }) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const presets = useQuery(taxRatePresetsQuery);
  const takeOver = useTakeOverPreset();
  const once = useRunOnce();
  const today = todayIso();

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("taxRates.presetsTitle")}</DialogTitle>
          <DialogDescription>{t("taxRates.presetsHint")}</DialogDescription>
        </DialogHeader>
        <FormAlert message={presets.isError ? errorMessage(presets.error) : null} />
        {presets.data === undefined ? (
          presets.isPending ? (
            <Skeleton className="h-32 w-full" />
          ) : null
        ) : presets.data.length === 0 ? (
          <p className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
            {t("taxRates.presetsNone")}
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {presets.data.map((preset) => {
              // Today's percentage, else the first one to come.
              const percent = percentOn(preset, today) ?? preset.values[0]?.percent;
              return (
                <li
                  key={preset.key}
                  className="flex flex-col gap-1.5 rounded-lg border p-3 text-sm"
                  aria-label={preset.name}
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex flex-wrap items-center gap-2 font-medium">
                      {preset.name}
                      <Badge variant="neutral" className="font-mono">
                        <span aria-hidden="true">{preset.category}</span>
                        <span className="sr-only">{t(`taxRates.category.${preset.category}`)}</span>
                      </Badge>
                    </span>
                    <span className="font-medium whitespace-nowrap tabular-nums">
                      {percent === undefined ? "" : formatPercent(percent, locale)}
                    </span>
                  </div>
                  {preset.notice === "" ? null : (
                    <p className="text-muted-foreground">
                      {t("taxRates.presetNotice", { notice: preset.notice })}
                    </p>
                  )}
                  {preset.sources.length === 0 ? null : (
                    <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground">
                      {preset.sources.map((source) => {
                        const { url, note } = sourceLink(source);
                        return (
                          <li key={source}>
                            {url === null ? (
                              note
                            ) : (
                              <>
                                <ExternalLink href={url} className="min-h-6 text-primary">
                                  {t("taxRates.source")}
                                </ExternalLink>{" "}
                                {note}
                              </>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="w-fit"
                    disabled={once.busy}
                    aria-label={t("taxRates.takeOverName", { name: preset.name })}
                    onClick={() =>
                      once.run(() =>
                        takeOver.mutateAsync(preset.key).then(
                          (rate) => {
                            toast.success(t("taxRates.takenOver", { name: rate.name }));
                            once.finish();
                            onClose();
                          },
                          (caught: unknown) => {
                            toast.error(errorMessage(caught));
                          },
                        ),
                      )
                    }
                  >
                    {t("taxRates.takeOver")}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
