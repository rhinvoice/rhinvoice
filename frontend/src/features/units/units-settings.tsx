import { useQuery } from "@tanstack/react-query";
import { ArrowDownIcon, ArrowUpIcon, GripVerticalIcon, LibraryIcon, PlusIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { FormAlert } from "@/features/shared/form-alert";
import { moved, moveTarget } from "@/features/shared/reorder-model";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { unitsQuery, useOrderUnits, type Unit } from "@/features/units/api";
import { UnitPresetDialog } from "@/features/units/unit-preset-dialog";
import { UnitDialog } from "@/features/units/unit-dialog";
import { cn } from "@/lib/cn";

/** The edited unit by id, or a new one. */
type Editing = { readonly id: string | null } | null;

/**
 * The units offered for lines and articles, in their order (ADR 0046, variant 1B): dragging a
 * unit or Alt+↑/↓ sorts them, a click opens one. Hidden units are not listed; they come back
 * through the catalogue.
 */
export function UnitsSettings() {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const units = useQuery(unitsQuery);
  const order = useOrderUnits();
  const [editing, setEditing] = useState<Editing>(null);
  const [presets, setPresets] = useState(false);
  const [dragging, setDragging] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const offered = (units.data ?? []).filter((unit) => !unit.hidden);
  // While the new order is saved, the list shows it already.
  const pending = order.isPending ? order.variables : undefined;
  const shown =
    pending === undefined
      ? offered
      : pending.flatMap((id) => offered.filter((unit) => unit.id === id));
  const edited: Unit | null =
    editing?.id === null || editing === null
      ? null
      : (units.data?.find((unit) => unit.id === editing.id) ?? null);

  const reorder = (from: number, to: number) => {
    const unit = shown[from];
    if (unit === undefined || from === to) return;
    setAnnouncement(t("units.moved", { label: unit.label, position: to + 1 }));
    order.mutate(
      moved(
        shown.map((item) => item.id),
        from,
        to,
      ),
      {
        onError: (caught) => {
          toast.error(errorMessage(caught));
        },
      },
    );
  };

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">{t("units.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("units.description")}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => {
              setPresets(true);
            }}
          >
            <LibraryIcon aria-hidden="true" />
            {t("units.fromPreset")}
          </Button>
          <Button
            onClick={() => {
              setEditing({ id: null });
            }}
          >
            <PlusIcon aria-hidden="true" />
            {t("units.add")}
          </Button>
        </div>
      </div>
      <FormAlert message={units.isError ? errorMessage(units.error) : null} />
      {units.data === undefined ? (
        units.isPending ? (
          <Skeleton className="h-64 w-full" />
        ) : null
      ) : (
        <>
          <p id="units-sort-hint" className="text-sm text-muted-foreground">
            {t("units.sortHint")}
          </p>
          <ol className="flex flex-col rounded-lg border" aria-label={t("units.title")}>
            {shown.map((unit, index) => (
              <li
                key={unit.id}
                className={cn(
                  "relative flex items-center gap-1 border-b pr-2 last:border-b-0",
                  dragging === index && "opacity-40",
                  dropTarget === index &&
                    dragging !== null &&
                    (dragging < index
                      ? "after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:rounded-full after:bg-primary"
                      : "before:absolute before:inset-x-0 before:-top-px before:h-0.5 before:rounded-full before:bg-primary"),
                )}
              >
                <button
                  type="button"
                  id={`unit-${unit.id}`}
                  // Dragging is the pointer shortcut; Alt+↑/↓ does the same (WCAG 2.5.7).
                  draggable
                  aria-label={t("units.edit", { label: unit.label })}
                  aria-describedby="units-sort-hint"
                  className="grid min-w-0 flex-1 grid-cols-[1.25rem_minmax(0,1fr)_auto] items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted focus-visible:bg-muted"
                  onClick={() => {
                    setEditing({ id: unit.id });
                  }}
                  onKeyDown={(event) => {
                    const to = moveTarget(event, index, shown.length);
                    if (to === null) return;
                    event.preventDefault();
                    reorder(index, to);
                    // Back to the unit at its new place, for keyboard users.
                    requestAnimationFrame(() => {
                      document.getElementById(`unit-${unit.id}`)?.focus();
                    });
                  }}
                  onDragStart={(event) => {
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", unit.id);
                    setDragging(index);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "move";
                    if (dragging !== null && dragging !== index) setDropTarget(index);
                  }}
                  onDragLeave={() => {
                    if (dropTarget === index) setDropTarget(null);
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    // Only a real drop moves; a cancelled drag (Esc, outside) does nothing.
                    if (dragging !== null && dragging !== index) reorder(dragging, index);
                    setDragging(null);
                    setDropTarget(null);
                  }}
                  onDragEnd={() => {
                    setDragging(null);
                    setDropTarget(null);
                  }}
                >
                  <GripVerticalIcon
                    className="size-4 cursor-grab text-muted-foreground"
                    aria-hidden="true"
                  />
                  <span className="flex min-w-0 flex-col">
                    <span className="font-medium break-words">{unit.label}</span>
                    {unit.description === "" ? null : (
                      <span className="text-xs break-words text-muted-foreground">
                        {unit.description}
                      </span>
                    )}
                  </span>
                  <Badge variant="neutral" className="font-mono" title={t("units.code")}>
                    {unit.code}
                  </Badge>
                </button>
                {/* Without dragging or keys (WCAG 2.5.7), e.g. on phones. */}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  disabled={index === 0}
                  aria-label={t("units.moveUp", { label: unit.label })}
                  onClick={() => {
                    reorder(index, index - 1);
                  }}
                >
                  <ArrowUpIcon aria-hidden="true" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  disabled={index === shown.length - 1}
                  aria-label={t("units.moveDown", { label: unit.label })}
                  onClick={() => {
                    reorder(index, index + 1);
                  }}
                >
                  <ArrowDownIcon aria-hidden="true" />
                </Button>
              </li>
            ))}
          </ol>
          <p className="sr-only" aria-live="polite">
            {announcement}
          </p>
        </>
      )}

      {editing === null || (editing.id !== null && edited === null) ? null : (
        <UnitDialog
          unit={edited}
          isLast={edited !== null && !edited.hidden && offered.length === 1}
          onClose={() => {
            setEditing(null);
          }}
        />
      )}
      {presets ? (
        <UnitPresetDialog
          onClose={() => {
            setPresets(false);
          }}
        />
      ) : null}
    </div>
  );
}
