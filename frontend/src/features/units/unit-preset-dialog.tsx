import { useQuery } from "@tanstack/react-query";
import { SearchIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useRunOnce } from "@/components/use-run-once";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { unitPresetsQuery, useTakeOverUnits } from "@/features/units/api";
import { chosenOffers, groupedOffers, offerKey, offerName } from "@/features/units/unit-form-model";
import { cn } from "@/lib/cn";

/**
 * Units from the catalogue and the hidden ones, searchable and grouped (ADR 0046, variant 3A);
 * several are taken over at once and go to the end of the list.
 */
export function UnitPresetDialog({ onClose }: { readonly onClose: () => void }) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const offers = useQuery(unitPresetsQuery);
  const takeOver = useTakeOverUnits();
  const once = useRunOnce();
  const [search, setSearch] = useState("");
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const groups = groupedOffers(offers.data ?? [], search, locale);
  const toggle = (key: string, checked: boolean) => {
    const next = new Set(chosen);
    if (checked) next.add(key);
    else next.delete(key);
    setChosen(next);
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("units.presetsTitle")}</DialogTitle>
          <DialogDescription>{t("units.presetsHint")}</DialogDescription>
        </DialogHeader>
        <FormAlert message={offers.isError ? errorMessage(offers.error) : null} />
        {offers.data === undefined ? (
          offers.isPending ? (
            <Skeleton className="h-48 w-full" />
          ) : null
        ) : offers.data.length === 0 ? (
          <p className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
            {t("units.presetsNone")}
          </p>
        ) : (
          <div className="flex min-h-0 flex-col gap-3">
            <div className="relative">
              <SearchIcon
                className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                type="search"
                className="pl-8"
                value={search}
                aria-label={t("units.search")}
                placeholder={t("units.search")}
                onChange={(event) => {
                  setSearch(event.target.value);
                }}
              />
            </div>
            <div className="flex max-h-[50vh] flex-col gap-4 overflow-y-auto pr-1">
              {groups.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("units.presetsNoMatch")}</p>
              ) : (
                groups.map(({ group, offers: entries }) => (
                  <fieldset key={group ?? "hidden"} className="flex flex-col gap-1">
                    <legend className="mb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                      {group === null ? t("units.groupHidden") : t(`units.group.${group}`)}
                    </legend>
                    {entries.map((offer) => {
                      const key = offerKey(offer);
                      const checked = chosen.has(key);
                      return (
                        <label
                          key={key}
                          className={cn(
                            "grid cursor-pointer grid-cols-[1rem_minmax(0,1fr)_auto] items-center gap-3 rounded-lg border px-3 py-2 text-sm transition-colors hover:bg-muted",
                            checked && "border-primary",
                          )}
                        >
                          <input
                            type="checkbox"
                            className="size-4 accent-primary"
                            checked={checked}
                            onChange={(event) => {
                              toggle(key, event.target.checked);
                            }}
                          />
                          <span className="min-w-0 break-words">{offerName(offer, locale)}</span>
                          <Badge variant="neutral" className="font-mono">
                            {offer.code}
                          </Badge>
                        </label>
                      );
                    })}
                  </fieldset>
                ))
              )}
            </div>
          </div>
        )}
        <DialogFooter className="sm:items-center">
          <p className="text-sm text-muted-foreground sm:mr-auto" aria-live="polite">
            {t("units.chosen", { count: chosen.size })}
          </p>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            type="button"
            disabled={chosen.size === 0}
            busy={once.busy}
            onClick={() =>
              once.run(() =>
                takeOver.mutateAsync(chosenOffers(offers.data ?? [], chosen)).then(
                  () => {
                    toast.success(t("units.takenOver", { count: chosen.size }));
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
            {t("units.takeOver")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
