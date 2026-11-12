import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState, type SyntheticEvent } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { PaperPreview } from "@/components/paper-preview";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { RadioCard } from "@/components/ui/radio-cards";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebouncedValue } from "@/components/use-debounced-value";
import { printLayoutPreviewQuery, useSavePrintLayout } from "@/features/company/api";
import { LayoutBar } from "@/features/company/layout-bar";
import { InfoBlockCard } from "@/features/company/info-block-card";
import { SwitchRow } from "@/features/company/switch-row";
import {
  printLayoutsQuery,
  type NamedLayout,
  type PrintLayout,
} from "@/features/shared/company-api";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { isField, isReferenceField, type InfoEntry } from "@/lib/info-block";

const PREVIEW_DELAY_MS = 300;

/** The part of the page each group of settings changes, to keep it in view. */
const AREAS = {
  head: "header.head",
  info: "dl.meta",
  lines: "table.lines",
  footer: "main > footer",
} as const;
type PageArea = keyof typeof AREAS;

const unnamed = (entry: InfoEntry) =>
  isField(entry) && !isReferenceField(entry.key) && entry.label.trim() === "";

export function PrintLayoutSettings() {
  const query = useQuery(printLayoutsQuery);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const layouts = query.data;
  if (layouts === undefined) {
    return query.isPending ? <Skeleton className="h-96" /> : null;
  }
  const selected =
    layouts.find((named) => named.id === selectedId) ?? layouts.find((named) => named.is_default);
  if (selected === undefined) return null;
  return (
    <PrintLayoutForm
      key={selected.id}
      named={selected}
      layouts={layouts}
      onSelect={setSelectedId}
    />
  );
}

interface PrintLayoutFormProps {
  readonly named: NamedLayout;
  readonly layouts: readonly NamedLayout[];
  readonly onSelect: (id: string) => void;
}

function PrintLayoutForm({ named, layouts, onSelect }: PrintLayoutFormProps) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSavePrintLayout();
  const saved = named.layout;
  const [layout, setLayout] = useState(saved);
  // A field just added has no name yet: the preview shows it under the default one.
  const debounced = useDebouncedValue(layout, PREVIEW_DELAY_MS);
  const preview = useQuery(
    printLayoutPreviewQuery({
      ...debounced,
      info_block: debounced.info_block.map((entry) =>
        unnamed(entry) ? { ...entry, label: t("printLayout.customDefault") } : entry,
      ),
    }),
  );
  const dirty = JSON.stringify(layout) !== JSON.stringify(saved);
  const missingName = layout.info_block.some(unnamed);
  // The preview follows what is being set up: the part of the page it changes.
  const [area, setArea] = useState<PageArea>("head");
  const paper = useRef<HTMLElement>(null);
  const showArea = useCallback(
    (page: Document | undefined) => {
      const container = paper.current;
      const frame = container?.querySelector("iframe");
      const target = page?.querySelector(AREAS[area]);
      if (
        container === null ||
        frame === null ||
        frame === undefined ||
        target === null ||
        target === undefined
      )
        return;
      const scale = frame.getBoundingClientRect().height / frame.offsetHeight;
      const top =
        frame.getBoundingClientRect().top -
        container.getBoundingClientRect().top +
        container.scrollTop +
        target.getBoundingClientRect().top * scale;
      const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      // A third from the top, so that what is around stays in view.
      container.scrollTo({
        top: Math.max(0, top - container.clientHeight / 3),
        behavior: smooth ? "smooth" : "auto",
      });
    },
    [area],
  );
  useEffect(() => {
    showArea(paper.current?.querySelector("iframe")?.contentDocument ?? undefined);
  }, [showArea]);
  const follow = (event: SyntheticEvent) => {
    const part = (event.target as Element).closest("[data-area]")?.getAttribute("data-area");
    if (part !== null && part !== undefined && part in AREAS) setArea(part as PageArea);
  };
  const change = (patch: Partial<PrintLayout>) => {
    setLayout((current) => ({ ...current, ...patch }));
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold">{t("printLayout.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("printLayout.description")}</p>
        </div>
        <LayoutBar
          named={named}
          layouts={layouts}
          layout={layout}
          dirty={dirty}
          onSelect={onSelect}
        />
      </div>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <div className="flex flex-col gap-4">
          <div
            className="flex flex-col gap-4"
            onFocusCapture={follow}
            onPointerDownCapture={follow}
          >
            <div data-area="head">
              <Choice
                legend={t("printLayout.template")}
                name="template"
                value={layout.template}
                options={(["classic", "modern", "plain"] as const).map((value) => [
                  value,
                  t(`printLayout.template.${value}`),
                  t(`printLayout.templateHint.${value}`),
                ])}
                onChange={(template) => {
                  change({ template });
                }}
              />
            </div>
            <Card aria-labelledby="print-logo-title" data-area="head">
              <CardHeader>
                <CardTitle id="print-logo-title">{t("printLayout.logoAndFont")}</CardTitle>
              </CardHeader>
              <Choice
                legend={t("printLayout.logoPosition")}
                name="logo_position"
                value={layout.logo_position}
                options={(["left", "right"] as const).map((value) => [
                  value,
                  t(`printLayout.logoPosition.${value}`),
                ])}
                onChange={(logo_position) => {
                  change({ logo_position });
                }}
              />
              <Choice
                legend={t("printLayout.logoSize")}
                name="logo_size"
                value={layout.logo_size}
                options={(["small", "medium", "large"] as const).map((value) => [
                  value,
                  t(`printLayout.logoSize.${value}`),
                ])}
                onChange={(logo_size) => {
                  change({ logo_size });
                }}
              />
              <Choice
                legend={t("printLayout.font")}
                name="font"
                value={layout.font}
                options={(["sans", "serif"] as const).map((value) => [
                  value,
                  t(`printLayout.font.${value}`),
                ])}
                onChange={(font) => {
                  change({ font });
                }}
              />
              <p className="text-sm text-muted-foreground">{t("printLayout.colourHint")}</p>
            </Card>
            <Card aria-labelledby="print-content-title" data-area="head">
              <CardHeader>
                <CardTitle id="print-content-title">{t("printLayout.content")}</CardTitle>
              </CardHeader>
              <SwitchRow
                id="print-sender-line"
                label={t("printLayout.senderLine")}
                hint={t("printLayout.senderLineHint")}
                checked={layout.sender_line}
                onChange={(sender_line) => {
                  change({ sender_line });
                }}
              />
              <SwitchRow
                id="print-contact"
                label={t("printLayout.contact")}
                hint={t("printLayout.contactHint")}
                checked={layout.contact}
                onChange={(contact) => {
                  change({ contact });
                }}
              />
              <SwitchRow
                id="print-position-numbers"
                label={t("printLayout.positionNumbers")}
                hint={t("printLayout.positionNumbersHint")}
                checked={layout.position_numbers}
                onChange={(position_numbers) => {
                  change({ position_numbers });
                }}
              />
            </Card>
            <div data-area="info">
              <InfoBlockCard
                entries={layout.info_block}
                onChange={(info_block) => {
                  change({ info_block });
                }}
              />
            </div>
          </div>
          <div
            className="flex flex-col gap-4"
            onFocusCapture={follow}
            onPointerDownCapture={follow}
          >
            <Card aria-labelledby="print-footer-title" data-area="footer">
              <CardHeader>
                <CardTitle id="print-footer-title">{t("printLayout.footer")}</CardTitle>
              </CardHeader>
              <Choice
                legend={t("printLayout.footerAccounts")}
                name="footer_accounts"
                value={layout.footer_accounts}
                options={(["all", "invoice_currency", "none"] as const).map((value) => [
                  value,
                  t(`printLayout.footerAccounts.${value}`),
                ])}
                onChange={(footer_accounts) => {
                  change({ footer_accounts });
                }}
              />
              <p className="text-sm text-muted-foreground">{t("printLayout.footerHint")}</p>
            </Card>
            <Card aria-labelledby="print-e-invoice-title" data-area="head">
              <CardHeader>
                <CardTitle id="print-e-invoice-title">{t("printLayout.eInvoiceTitle")}</CardTitle>
              </CardHeader>
              <SwitchRow
                id="print-e-invoice"
                label={t("printLayout.eInvoice")}
                hint={t("printLayout.eInvoiceHint")}
                checked={layout.e_invoice}
                onChange={(e_invoice) => {
                  change({ e_invoice });
                }}
              />
            </Card>
          </div>
          <FormAlert
            message={
              missingName
                ? t("printLayout.customLabelRequired")
                : save.isError
                  ? errorMessage(save.error)
                  : null
            }
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button
              disabled={!dirty || missingName || save.isPending}
              onClick={() => {
                save.mutate(
                  { id: named.id, name: named.name, layout },
                  { onSuccess: () => toast.success(t("common.saved")) },
                );
              }}
            >
              {t("common.save")}
            </Button>
            <Button
              variant="outline"
              disabled={!dirty}
              onClick={() => {
                setLayout(saved);
              }}
            >
              {t("printLayout.reset")}
            </Button>
            <p className="text-sm text-muted-foreground">{t("printLayout.issuedStay")}</p>
          </div>
        </div>
        <div className="flex min-w-0 flex-col gap-2 xl:sticky xl:top-[calc(var(--topbar-height)+1rem)] xl:self-start">
          <p className="text-sm text-muted-foreground">{t("printLayout.previewHint")}</p>
          <FormAlert message={preview.isError ? errorMessage(preview.error) : null} />
          <section
            ref={paper}
            aria-label={t("printLayout.preview")}
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrolling region must be reachable by keyboard (WCAG 2.1.1, axe scrollable-region-focusable)
            tabIndex={0}
            className="rounded-md xl:max-h-[calc(100dvh-var(--topbar-height)-6rem)] xl:overflow-y-auto xl:overscroll-contain"
          >
            <PaperPreview
              html={preview.data}
              title={t("printLayout.preview")}
              busy={preview.isFetching}
              className="max-w-3xl"
            />
          </section>
        </div>
      </div>
    </div>
  );
}

interface ChoiceProps<V extends string> {
  readonly legend: string;
  readonly name: string;
  readonly value: V;
  /** Value, label and an optional hint per option. */
  readonly options: readonly (readonly [V, string, string?])[];
  readonly onChange: (value: V) => void;
}

/** Radio buttons as cards (keyboard: arrow keys). */
function Choice<V extends string>({ legend, name, value, options, onChange }: ChoiceProps<V>) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1.5 text-sm font-medium">{legend}</legend>
      <div className="grid gap-2 sm:grid-cols-[repeat(auto-fit,minmax(8rem,1fr))]">
        {options.map(([option, label, hint]) => (
          <div key={option} className="flex flex-col gap-1">
            <RadioCard
              id={`${name}-${option}`}
              name={name}
              value={option}
              label={label}
              checked={value === option}
              aria-describedby={hint === undefined ? undefined : `${name}-${option}-hint`}
              onChange={() => {
                onChange(option);
              }}
            />
            {hint === undefined ? null : (
              <p id={`${name}-${option}-hint`} className="px-1 text-xs text-muted-foreground">
                {hint}
              </p>
            )}
          </div>
        ))}
      </div>
    </fieldset>
  );
}
