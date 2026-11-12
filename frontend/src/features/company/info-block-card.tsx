import { ArrowDownIcon, ArrowUpIcon, GripVerticalIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  MAX_CUSTOM_FIELDS,
  MAX_FIELD_LABEL,
  REFERENCE_FIELDS,
  REQUIRED_ROWS,
  addField,
  customFieldCount,
  entryName,
  isReferenceField,
  isRow,
  missingReferenceFields,
  move,
  newCustomKey,
  removeField,
  rename,
  setShown,
  type InfoEntry,
} from "@/lib/info-block";
import { cn } from "@/lib/cn";

interface InfoBlockCardProps {
  readonly entries: readonly InfoEntry[];
  readonly onChange: (entries: InfoEntry[]) => void;
}

/** The facts next to the address: sort, show or hide rows, add and remove fields (#62, #60). */
export function InfoBlockCard({ entries, onChange }: InfoBlockCardProps) {
  const { t } = useI18n();
  const [dragged, setDragged] = useState<number | null>(null);
  const missing = missingReferenceFields(entries);
  const customFull = customFieldCount(entries) >= MAX_CUSTOM_FIELDS;

  return (
    <Card aria-labelledby="print-info-title">
      <CardHeader>
        <CardTitle id="print-info-title">{t("printLayout.infoBlock")}</CardTitle>
      </CardHeader>
      <p id="print-info-hint" className="text-sm text-muted-foreground">
        {t("printLayout.infoBlockHint")}
      </p>
      <ol className="flex flex-col gap-1.5" aria-describedby="print-info-hint">
        {entries.map((entry, index) => (
          <InfoRowItem
            key={entry.key}
            entry={entry}
            name={entryName(entry, t)}
            index={index}
            count={entries.length}
            dragging={dragged === index}
            onMove={(to) => {
              onChange(move(entries, index, to));
            }}
            onShown={(shown) => {
              onChange(setShown(entries, entry.key, shown));
            }}
            onRename={(label) => {
              onChange(rename(entries, entry.key, label));
            }}
            onRemove={() => {
              onChange(removeField(entries, entry.key));
            }}
            onDragStart={() => {
              setDragged(index);
            }}
            onDrop={() => {
              if (dragged !== null) onChange(move(entries, dragged, index));
              setDragged(null);
            }}
            onDragEnd={() => {
              setDragged(null);
            }}
          />
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="outline" size="sm">
              <PlusIcon aria-hidden="true" />
              {t("printLayout.addField")}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-64">
            {missing.length === 0 ? null : (
              <>
                <DropdownMenuLabel>{t("printLayout.addFieldReference")}</DropdownMenuLabel>
                {missing.map((key) => (
                  <DropdownMenuItem
                    key={key}
                    onSelect={() => {
                      onChange(addField(entries, key));
                    }}
                  >
                    <span className="flex-1">{t(`printLayout.field.${key}`)}</span>
                    <span className="text-xs text-muted-foreground">{REFERENCE_FIELDS[key]}</span>
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuItem
              disabled={customFull}
              onSelect={() => {
                onChange(addField(entries, newCustomKey(entries)));
              }}
            >
              {t("printLayout.addFieldCustom")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {customFull ? (
          <p className="text-sm text-muted-foreground">
            {t("printLayout.customLimit", { max: MAX_CUSTOM_FIELDS })}
          </p>
        ) : null}
      </div>
    </Card>
  );
}

interface InfoRowItemProps {
  readonly entry: InfoEntry;
  readonly name: string;
  readonly index: number;
  readonly count: number;
  readonly dragging: boolean;
  readonly onMove: (to: number) => void;
  readonly onShown: (shown: boolean) => void;
  readonly onRename: (label: string) => void;
  readonly onRemove: () => void;
  readonly onDragStart: () => void;
  readonly onDrop: () => void;
  readonly onDragEnd: () => void;
}

/** Alt+↑/↓ reorders without dragging (WCAG 2.5.7), as in the positions of a document. */
function moveTarget(event: KeyboardEvent<HTMLElement>, index: number, count: number) {
  if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return null;
  const to = event.key === "ArrowUp" ? index - 1 : index + 1;
  return to >= 0 && to < count ? to : null;
}

function InfoRowItem({
  entry,
  name,
  index,
  count,
  dragging,
  onMove,
  onShown,
  onRename,
  onRemove,
  onDragStart,
  onDrop,
  onDragEnd,
}: InfoRowItemProps) {
  const { t } = useI18n();
  const id = `print-info-${entry.key}`;
  const row = isRow(entry.key);
  const required = REQUIRED_ROWS.has(entry.key);
  const term = isReferenceField(entry.key) ? REFERENCE_FIELDS[entry.key] : null;
  const custom = !row && term === null;
  const serviceHidden = entry.key === "service_date" && !entry.shown;

  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- only the drop target of a drag; keyboards reorder with Alt+↑/↓ on the grip and the arrow buttons (WCAG 2.5.7)
    <li
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-md border bg-card px-2 py-1.5",
        !row && "border-primary/30 bg-primary/5",
        dragging && "opacity-50",
      )}
      onDragOver={(event) => {
        event.preventDefault();
      }}
      onDrop={(event) => {
        event.preventDefault();
        onDrop();
      }}
    >
      <button
        type="button"
        id={`${id}-grip`}
        // Dragging is the pointer shortcut; Alt+↑/↓ and the arrows do the same (WCAG 2.5.7).
        draggable
        className="flex size-7 shrink-0 cursor-grab items-center justify-center rounded-sm text-muted-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        aria-label={t("printLayout.reorder", { label: name })}
        onDragStart={(event) => {
          event.dataTransfer.effectAllowed = "move";
          onDragStart();
        }}
        onDragEnd={onDragEnd}
        onKeyDown={(event) => {
          const to = moveTarget(event, index, count);
          if (to === null) return;
          event.preventDefault();
          onMove(to);
        }}
      >
        <GripVerticalIcon aria-hidden="true" className="size-4" />
      </button>
      {custom ? (
        <Input
          id={id}
          className="h-8 min-w-0 flex-1"
          value={entry.label}
          maxLength={MAX_FIELD_LABEL}
          placeholder={t("printLayout.customDefault")}
          aria-label={t("printLayout.customLabel", { name: t("printLayout.customDefault") })}
          aria-invalid={entry.label.trim() === ""}
          onChange={(event) => {
            onRename(event.target.value);
          }}
        />
      ) : (
        <label htmlFor={row && !required ? id : undefined} className="min-w-0 flex-1 text-sm">
          {name}
        </label>
      )}
      {term === null ? null : (
        <Badge variant="info" title={t("printLayout.eInvoiceBadgeHint", { term })}>
          {t("printLayout.eInvoiceBadge")}
        </Badge>
      )}
      {required ? <Badge>{t("printLayout.required")}</Badge> : null}
      {row && !required ? (
        <Switch
          id={id}
          checked={entry.shown}
          onCheckedChange={onShown}
          aria-label={t("printLayout.show", { label: name })}
          aria-describedby={serviceHidden ? `${id}-warning` : undefined}
        />
      ) : null}
      <span className="flex gap-0.5">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          disabled={index === 0}
          onClick={() => {
            onMove(index - 1);
          }}
          aria-label={t("printLayout.moveUp", { label: name })}
        >
          <ArrowUpIcon aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          disabled={index === count - 1}
          onClick={() => {
            onMove(index + 1);
          }}
          aria-label={t("printLayout.moveDown", { label: name })}
        >
          <ArrowDownIcon aria-hidden="true" />
        </Button>
        {row ? null : (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={onRemove}
            aria-label={t("printLayout.remove", { label: name })}
          >
            <Trash2Icon aria-hidden="true" />
          </Button>
        )}
      </span>
      {serviceHidden ? (
        <p
          id={`${id}-warning`}
          role="note"
          className="basis-full rounded-md border border-warning/40 bg-warning/10 px-2.5 py-1.5 text-sm"
        >
          {t("printLayout.serviceDateWarning")}
        </p>
      ) : null}
    </li>
  );
}
