import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  CircleAlertIcon,
  GripVerticalIcon,
  PencilIcon,
  PlusIcon,
  TextIcon,
  Trash2Icon,
} from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import {
  Controller,
  useFieldArray,
  useFormContext,
  useWatch,
  type FieldError,
} from "react-hook-form";

import { useI18n } from "@/components/i18n/use-i18n";
import { Autocomplete } from "@/components/ui/autocomplete";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { useDebouncedValue } from "@/components/use-debounced-value";
import {
  articleOptionsQuery,
  type ArticleOption,
  type TaxTreatment,
} from "@/features/documents/api";
import {
  emptyLine,
  fieldId,
  lineFromArticle,
  lineRates,
  MAX_LINES,
  ownTreatment,
  SUPPLIES,
  TAX_CATEGORIES,
  type DocumentFormValues,
  type LineFormValues,
} from "@/features/documents/document-form-model";
import { taxCategoryLabel, type CountryProfile } from "@/features/shared/country-profile-model";
import { unitsQuery } from "@/features/shared/reference-api";
import { cn } from "@/lib/cn";
import { formatMoney, formatNumber, formatPercent } from "@/lib/format";
import { parseDecimal } from "@/lib/format/parse-decimal";
import { germanOrEnglish } from "@/lib/locale";

function ErrorText({ id, error }: { readonly id: string; readonly error: FieldError | undefined }) {
  if (error?.message === undefined) return null;
  return (
    <p id={id} className="flex items-start gap-1 text-xs text-destructive">
      <CircleAlertIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      {error.message}
    </p>
  );
}

type Rates = Partial<Record<(typeof TAX_CATEGORIES)[number], string>>;

interface LineItemsProps {
  /** Line amounts after the line discount, by index (null for text lines). */
  readonly amounts: readonly (string | null)[];
  /** Rate per tax category for this document; undefined until known. */
  readonly rates: Rates | undefined;
  /** The company's country: names the rates (e.g. "Sondersatz Beherbergung"). */
  readonly profile: CountryProfile;
  /** Treatment of goods lines when it differs from the document's (e.g. export). */
  readonly goodsTreatment: TaxTreatment | null | undefined;
  /** Index of the line being edited, null when all lines are closed. */
  readonly editing: number | null;
  readonly onEditingChange: (index: number | null) => void;
}

/**
 * The lines as a calm list: a click opens a line for editing, "Apply" closes it
 * again and "Cancel" restores what it was. Lines with errors stay open.
 */
export function LineItems({
  amounts,
  rates,
  profile,
  goodsTreatment,
  editing,
  onEditingChange,
}: LineItemsProps) {
  const { t } = useI18n();
  const { control, formState, getValues, setValue } = useFormContext<DocumentFormValues>();
  const { fields, append, insert, remove, move } = useFieldArray({ control, name: "lines" });
  const linesError = formState.errors.lines;
  const rootMessage = linesError?.root?.message ?? linesError?.message;
  // The open line as it was when it was opened, for "Cancel"; null for a new line.
  const [snapshot, setSnapshot] = useState<{
    readonly index: number;
    readonly line: LineFormValues | null;
  } | null>(null);
  // A line can also be opened from outside, e.g. by a click on the paper preview.
  if (editing !== null && snapshot?.index !== editing) {
    setSnapshot({ index: editing, line: getValues(`lines.${editing}`) });
  }
  const original = snapshot?.index === editing ? snapshot.line : null;

  // Dragging a closed line onto another moves it there (also possible with Alt+↑/↓).
  const [dragging, setDragging] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);

  const open = (index: number) => {
    setSnapshot({ index, line: getValues(`lines.${index}`) });
    onEditingChange(index);
  };
  const add = (kind: "item" | "text", index = fields.length) => {
    const focusName = `lines.${String(index)}.description` as const;
    if (index === fields.length) append(emptyLine(kind), { focusName });
    else insert(index, emptyLine(kind), { focusName });
    setSnapshot({ index, line: null });
    onEditingChange(index);
  };
  const close = (index: number) => {
    setSnapshot(null);
    onEditingChange(null);
    // Back to the line in the list, for keyboard users.
    requestAnimationFrame(() => {
      document.getElementById(`line-${String(index)}-summary`)?.focus();
    });
  };
  const cancel = (index: number) => {
    if (original === null) {
      remove(index);
      setSnapshot(null);
      onEditingChange(null);
      return;
    }
    setValue(`lines.${index}`, original, { shouldDirty: true, shouldValidate: true });
    close(index);
  };
  const reorder = (from: number, to: number) => {
    move(from, to);
    if (editing === from) {
      setSnapshot((current) => (current === null ? null : { ...current, index: to }));
      onEditingChange(to);
    }
  };

  return (
    <div className="flex flex-col gap-3" id={fieldId("lines")} tabIndex={-1}>
      {fields.length === 0 ? (
        <p className="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
          {t("documents.noLines")}
        </p>
      ) : (
        <ol className="flex flex-col">
          {fields.map((field, index) => {
            const errors = formState.errors.lines?.[index];
            return editing === index || errors !== undefined ? (
              <LineEditor
                key={field.id}
                index={index}
                count={fields.length}
                rates={rates}
                profile={profile}
                goodsTreatment={goodsTreatment}
                isNew={editing === index && original === null}
                onApply={() => {
                  close(index);
                }}
                onCancel={() => {
                  cancel(index);
                }}
                onMove={(to) => {
                  reorder(index, to);
                }}
                onRemove={() => {
                  remove(index);
                  setSnapshot(null);
                  onEditingChange(null);
                }}
              />
            ) : (
              <LineSummary
                key={field.id}
                index={index}
                count={fields.length}
                amount={amounts[index] ?? null}
                dragState={
                  dragging === index
                    ? "dragging"
                    : dropTarget === index && dragging !== null
                      ? // The line lands below the target when it comes from above.
                        dragging < index
                        ? "below"
                        : "above"
                      : "none"
                }
                onOpen={() => {
                  open(index);
                }}
                onMove={(to) => {
                  reorder(index, to);
                }}
                onDragStart={() => {
                  setDragging(index);
                }}
                onDragOver={() => {
                  if (dragging !== null && dragging !== index) setDropTarget(index);
                }}
                onDragLeave={() => {
                  if (dropTarget === index) setDropTarget(null);
                }}
                onDrop={() => {
                  // Only a real drop moves; a cancelled drag (Esc, outside) does nothing.
                  if (dragging !== null && dragging !== index) reorder(dragging, index);
                  setDragging(null);
                  setDropTarget(null);
                }}
                onDragEnd={() => {
                  setDragging(null);
                  setDropTarget(null);
                }}
              />
            );
          })}
        </ol>
      )}
      {typeof rootMessage === "string" ? (
        <p className="flex items-center gap-1.5 text-sm text-destructive">
          <CircleAlertIcon className="size-4" aria-hidden="true" />
          {rootMessage}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={fields.length >= MAX_LINES}
          onClick={() => {
            add("item");
          }}
        >
          <PlusIcon aria-hidden="true" />
          {t("documents.addLine")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={fields.length >= MAX_LINES}
          onClick={() => {
            add("text");
          }}
        >
          <TextIcon aria-hidden="true" />
          {t("documents.addTextLine")}
        </Button>
      </div>
    </div>
  );
}

/** Alt+↑/↓ reorders lines without dragging (WCAG 2.5.7). */
function moveTarget(event: KeyboardEvent<HTMLElement>, index: number, count: number) {
  if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return null;
  const to = event.key === "ArrowUp" ? index - 1 : index + 1;
  return to >= 0 && to < count ? to : null;
}

interface LineSummaryProps {
  readonly index: number;
  readonly count: number;
  readonly amount: string | null;
  readonly dragState: "none" | "dragging" | "above" | "below";
  readonly onOpen: () => void;
  readonly onMove: (to: number) => void;
  readonly onDragStart: () => void;
  readonly onDragOver: () => void;
  readonly onDragLeave: () => void;
  readonly onDrop: () => void;
  readonly onDragEnd: () => void;
}

function LineSummary({
  index,
  count,
  amount,
  dragState,
  onOpen,
  onMove,
  onDragStart,
  onDragOver,
  onDragLeave,
  onDrop,
  onDragEnd,
}: LineSummaryProps) {
  const { t, locale } = useI18n();
  const { control } = useFormContext<DocumentFormValues>();
  const units = useQuery(unitsQuery);
  const line = useWatch({ control, name: `lines.${index}` });
  const currency = useWatch({ control, name: "currency" });
  const number = index + 1;
  const unit = units.data?.find((candidate) => candidate.code === line.unit);
  const unitLabel = unit === undefined ? "" : germanOrEnglish(locale, unit.label_de, unit.label_en);
  const isItem = line.kind === "item";
  // What the user typed, in the number format of the language; unparsable input as typed.
  const display = (input: string, format: (value: string) => string) => {
    const value = parseDecimal(input, locale);
    return value === null ? input : format(value);
  };
  return (
    <li
      className={cn(
        "relative border-b transition-opacity last:border-b-0",
        dragState === "dragging" && "opacity-40",
        dragState === "above" &&
          "before:absolute before:inset-x-0 before:-top-px before:h-0.5 before:rounded-full before:bg-primary",
        dragState === "below" &&
          "after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:rounded-full after:bg-primary",
      )}
    >
      <button
        type="button"
        id={`line-${String(index)}-summary`}
        // Dragging is the pointer shortcut; Alt+↑/↓ and the editor's arrows do the same.
        draggable
        onDragStart={(event) => {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", String(index));
          onDragStart();
        }}
        onDragOver={(event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
          onDragOver();
        }}
        onDragLeave={onDragLeave}
        onDrop={(event) => {
          event.preventDefault();
          onDrop();
        }}
        onDragEnd={onDragEnd}
        aria-label={t("documents.editLine", { number, description: line.description })}
        className="group -mx-2 grid w-[calc(100%+1rem)] grid-cols-[1.75rem_minmax(0,1fr)_auto] items-start gap-x-3 gap-y-0.5 rounded-md px-2 py-3 text-left transition-colors hover:bg-muted focus-visible:bg-muted"
        onClick={onOpen}
        onKeyDown={(event) => {
          const to = moveTarget(event, index, count);
          if (to === null) return;
          event.preventDefault();
          onMove(to);
          requestAnimationFrame(() => {
            document.getElementById(`line-${String(to)}-summary`)?.focus();
          });
        }}
      >
        <span className="relative text-sm text-muted-foreground tabular-nums">
          <span className="group-hover:invisible">{isItem ? number : ""}</span>
          <GripVerticalIcon
            className="invisible absolute top-0.5 left-0 size-4 cursor-grab group-hover:visible"
            aria-hidden="true"
          />
        </span>
        <span className="flex min-w-0 flex-col">
          <span className={cn("break-words", isItem ? "font-medium" : "font-semibold")}>
            {line.description}
          </span>
          {line.details === "" ? null : (
            <span className="text-sm break-words whitespace-pre-line text-muted-foreground">
              {line.details}
            </span>
          )}
          {isItem ? (
            <span className="text-sm text-muted-foreground tabular-nums">
              {display(line.quantity, (value) => formatNumber(value, locale, 4))} {unitLabel} ×{" "}
              {display(line.unit_price === "" ? "0" : line.unit_price, (value) =>
                formatMoney(value, currency, locale, 4),
              )}
              {line.discount_percent === "" || line.discount_percent === "0"
                ? ""
                : ` · −${display(line.discount_percent, (value) => formatNumber(value, locale, 2))} %`}
              {line.supply === "goods" ? ` · ${t("supply.goods")}` : ""}
            </span>
          ) : null}
        </span>
        <span className="flex items-center gap-2 text-right font-semibold tabular-nums">
          {isItem && amount !== null ? formatMoney(amount, currency, locale) : ""}
          <PencilIcon
            className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
            aria-hidden="true"
          />
        </span>
      </button>
    </li>
  );
}

interface LineEditorProps {
  readonly rates: Rates | undefined;
  readonly profile: CountryProfile;
  readonly goodsTreatment: TaxTreatment | null | undefined;
  readonly index: number;
  readonly count: number;
  readonly isNew: boolean;
  readonly onApply: () => void;
  readonly onCancel: () => void;
  readonly onMove: (to: number) => void;
  readonly onRemove: () => void;
}

function LineEditor({
  index,
  count,
  rates,
  profile,
  goodsTreatment,
  isNew,
  onApply,
  onCancel,
  onMove,
  onRemove,
}: LineEditorProps) {
  const { t, locale } = useI18n();
  const { control, register, formState, getValues, setValue, trigger } =
    useFormContext<DocumentFormValues>();
  const units = useQuery(unitsQuery);
  const kind = useWatch({ control, name: `lines.${index}.kind` });
  const currency = useWatch({ control, name: "currency" });
  const details = useWatch({ control, name: `lines.${index}.details` });
  const taxCategory = useWatch({ control, name: `lines.${index}.tax_category` });
  const supply = useWatch({ control, name: `lines.${index}.supply` });
  const own = ownTreatment(supply, goodsTreatment);
  const offered = lineRates(rates, own);
  const [showDetails, setShowDetails] = useState(false);
  const errors = formState.errors.lines?.[index];
  const number = index + 1;
  const path = (field: string) => `lines.${String(index)}.${field}`;
  const id = (field: string) => fieldId(path(field));
  const describedBy = (field: keyof NonNullable<typeof errors>) =>
    errors?.[field] === undefined ? undefined : `${id(field)}-error`;
  const isItem = kind === "item";

  const apply = async () => {
    // Only a complete line closes; otherwise its errors show right here.
    if (await trigger(`lines.${index}`)) onApply();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const to = moveTarget(event, index, count);
    if (to !== null) {
      event.preventDefault();
      onMove(to);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
    }
  };
  // ↵ in a field applies the line (⌘↵ still saves the whole document).
  const onEnter = (event: KeyboardEvent<HTMLInputElement>) => {
    onKeyDown(event);
    if (event.key !== "Enter" || event.metaKey || event.ctrlKey || event.defaultPrevented) return;
    event.preventDefault();
    void apply();
  };

  return (
    <li
      aria-label={t("documents.lineLabel", { number })}
      className="my-2 flex flex-col gap-3 rounded-lg border border-primary/50 bg-card p-4 shadow-sm ring-3 ring-ring/15"
    >
      <div className="flex flex-col gap-1.5">
        <label htmlFor={id("description")} className="text-sm font-medium">
          {isItem ? t("documents.lineDescription") : t("documents.lineText")}
        </label>
        <Controller
          control={control}
          name={`lines.${index}.description`}
          render={({ field }) => (
            <ArticleAutocomplete
              id={id("description")}
              inputRef={field.ref}
              value={field.value}
              enabled={isItem}
              aria-invalid={errors?.description === undefined ? undefined : true}
              aria-describedby={describedBy("description")}
              onChange={field.onChange}
              onBlur={field.onBlur}
              onKeyDown={onEnter}
              onPick={(article) => {
                setValue(
                  `lines.${index}`,
                  lineFromArticle(getValues(`lines.${index}`), article, currency, locale),
                  { shouldDirty: true, shouldValidate: true },
                );
                setShowDetails(article.description !== "");
              }}
            />
          )}
        />
        <ErrorText id={`${id("description")}-error`} error={errors?.description} />
        {showDetails || details !== "" ? (
          <>
            <label htmlFor={id("details")} className="sr-only">
              {t("documents.lineDetails", { number })}
            </label>
            <Textarea
              id={id("details")}
              onKeyDown={onKeyDown}
              rows={2}
              className="min-h-14"
              placeholder={t("documents.lineDetailsPlaceholder")}
              {...register(`lines.${index}.details`)}
            />
          </>
        ) : (
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-6 w-fit px-0 text-xs"
            onClick={() => {
              setShowDetails(true);
            }}
          >
            {t("documents.addDetails")}
            <span className="sr-only">{t("documents.lineLabel", { number })}</span>
          </Button>
        )}
      </div>

      {isItem ? (
        <div className="grid grid-cols-2 gap-3 @lg:grid-cols-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor={id("quantity")} className="text-sm font-medium">
              {t("documents.lineQuantity")}
            </label>
            <Input
              id={id("quantity")}
              inputMode="decimal"
              className="text-right tabular-nums"
              aria-invalid={errors?.quantity === undefined ? undefined : true}
              aria-describedby={describedBy("quantity")}
              onKeyDown={onEnter}
              {...register(`lines.${index}.quantity`)}
            />
            <ErrorText id={`${id("quantity")}-error`} error={errors?.quantity} />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={id("unit")} className="text-sm font-medium">
              {t("documents.lineUnit")}
            </label>
            <NativeSelect
              id={id("unit")}
              onKeyDown={onKeyDown}
              {...register(`lines.${index}.unit`)}
            >
              <option value="">{t("common.none")}</option>
              {(units.data ?? []).map((unit) => (
                <option key={unit.code} value={unit.code}>
                  {germanOrEnglish(locale, unit.label_de, unit.label_en)}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={id("unit_price")} className="text-sm font-medium">
              {t("documents.linePriceIn", { currency })}
            </label>
            <Input
              id={id("unit_price")}
              inputMode="decimal"
              className="text-right tabular-nums"
              aria-invalid={errors?.unit_price === undefined ? undefined : true}
              aria-describedby={describedBy("unit_price")}
              onKeyDown={onEnter}
              {...register(`lines.${index}.unit_price`)}
            />
            <ErrorText id={`${id("unit_price")}-error`} error={errors?.unit_price} />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor={id("discount_percent")} className="text-sm font-medium">
              {t("documents.lineDiscount")}
            </label>
            <Input
              id={id("discount_percent")}
              inputMode="decimal"
              className="text-right tabular-nums"
              aria-invalid={errors?.discount_percent === undefined ? undefined : true}
              aria-describedby={describedBy("discount_percent")}
              onKeyDown={onEnter}
              {...register(`lines.${index}.discount_percent`)}
            />
            <ErrorText id={`${id("discount_percent")}-error`} error={errors?.discount_percent} />
          </div>
          <div className="col-span-2 flex flex-col gap-1.5">
            <label htmlFor={id("tax_category")} className="text-sm font-medium">
              {t("documents.lineTax")}
            </label>
            <NativeSelect
              id={id("tax_category")}
              onKeyDown={onKeyDown}
              {...register(`lines.${index}.tax_category`)}
            >
              {TAX_CATEGORIES.filter(
                // Categories without a rate in the country (e.g. no special rate in DE)
                // are not offered, unless the line already uses one.
                (category) => rates === undefined || category in rates || category === taxCategory,
              ).map((category) => {
                const rate = offered?.[category];
                const label = taxCategoryLabel(category, profile, locale, t);
                return (
                  <option key={category} value={category}>
                    {rate === undefined ? label : `${label} (${formatPercent(rate, locale)})`}
                  </option>
                );
              })}
            </NativeSelect>
          </div>
          <div className="col-span-2 flex flex-col gap-1.5">
            <label htmlFor={id("supply")} className="text-sm font-medium">
              {t("documents.lineSupply")}
            </label>
            <NativeSelect
              id={id("supply")}
              aria-describedby={own === null ? undefined : `${id("supply")}-treatment`}
              onKeyDown={onKeyDown}
              {...register(`lines.${index}.supply`)}
            >
              {SUPPLIES.map((option) => (
                <option key={option} value={option}>
                  {t(`supply.${option}`)}
                </option>
              ))}
            </NativeSelect>
            {own === null ? null : (
              <p id={`${id("supply")}-treatment`} className="text-xs text-muted-foreground">
                {t("documents.goodsTreatment", { treatment: t(`treatment.${own}`) })}
              </p>
            )}
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={() => void apply()}>
          <CheckIcon aria-hidden="true" />
          {t("documents.applyLine")}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onCancel}>
          {isNew ? t("documents.discardLine") : t("common.cancel")}
        </Button>
        <span className="ml-auto flex gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={index === 0}
            onClick={() => {
              onMove(index - 1);
            }}
            aria-label={t("documents.moveUp", { number })}
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
            aria-label={t("documents.moveDown", { number })}
          >
            <ArrowDownIcon aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={onRemove}
            aria-label={t("documents.removeLine", { number })}
          >
            <Trash2Icon aria-hidden="true" />
          </Button>
        </span>
      </div>
    </li>
  );
}

interface ArticleAutocompleteProps {
  readonly id: string;
  readonly inputRef: (element: HTMLInputElement | null) => void;
  readonly value: string;
  readonly enabled: boolean;
  readonly onChange: (value: string) => void;
  readonly onBlur: () => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLInputElement>) => void;
  readonly onPick: (article: ArticleOption) => void;
  readonly "aria-invalid": boolean | undefined;
  readonly "aria-describedby": string | undefined;
}

/** Description input of a line that suggests articles while typing (from 2 characters). */
function ArticleAutocomplete({
  id,
  inputRef,
  value,
  enabled,
  onChange,
  onBlur,
  onKeyDown,
  onPick,
  ...aria
}: ArticleAutocompleteProps) {
  const { t, locale } = useI18n();
  const [typing, setTyping] = useState(false);
  const term = useDebouncedValue(value.trim(), 200);
  const articles = useQuery({
    ...articleOptionsQuery(term),
    enabled: enabled && typing && term.length >= 2,
  });
  return (
    <Autocomplete
      id={id}
      ref={inputRef}
      value={value}
      minLength={2}
      listLabel={t("articles.title")}
      countLabel={(count) => t("common.results", { count })}
      onValueChange={(next) => {
        setTyping(true);
        onChange(next);
      }}
      onBlur={() => {
        setTyping(false);
        onBlur();
      }}
      onKeyDown={onKeyDown}
      options={enabled && typing ? (articles.data?.items ?? []) : []}
      optionKey={(article) => article.id}
      onSelect={(article) => {
        setTyping(false);
        onPick(article);
      }}
      renderOption={(article) => (
        <>
          <span className="font-medium">{article.name}</span>
          <span className="text-xs text-muted-foreground">
            {article.number}
            {Object.entries(article.prices).map(([currency, price]) => (
              <span key={currency}> · {formatMoney(price, currency, locale, 4)}</span>
            ))}
          </span>
        </>
      )}
      {...(aria["aria-invalid"] === undefined ? {} : { "aria-invalid": aria["aria-invalid"] })}
      {...(aria["aria-describedby"] === undefined
        ? {}
        : { "aria-describedby": aria["aria-describedby"] })}
      {...(enabled ? {} : { placeholder: t("documents.lineTextPlaceholder") })}
    />
  );
}
