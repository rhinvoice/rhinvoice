import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { PaperPreview } from "@/components/paper-preview";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { RadioCard } from "@/components/ui/radio-cards";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebouncedValue } from "@/components/use-debounced-value";
import {
  printLayoutPreviewQuery,
  printLayoutQuery,
  useSavePrintLayout,
  type PrintLayout,
} from "@/features/company/api";
import { SwitchRow } from "@/features/company/switch-row";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";

const PREVIEW_DELAY_MS = 300;

export function PrintLayoutSettings() {
  const query = useQuery(printLayoutQuery);
  if (query.data === undefined) {
    return query.isPending ? <Skeleton className="h-96" /> : null;
  }
  return <PrintLayoutForm saved={query.data} />;
}

function PrintLayoutForm({ saved }: { readonly saved: PrintLayout }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSavePrintLayout();
  const [layout, setLayout] = useState(saved);
  const preview = useQuery(printLayoutPreviewQuery(useDebouncedValue(layout, PREVIEW_DELAY_MS)));
  const dirty = JSON.stringify(layout) !== JSON.stringify(saved);
  const change = (patch: Partial<PrintLayout>) => {
    setLayout((current) => ({ ...current, ...patch }));
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
      <div className="flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold">{t("printLayout.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("printLayout.description")}</p>
        </div>
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
        <Card aria-labelledby="print-logo-title">
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
        <Card aria-labelledby="print-content-title">
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
        <Card aria-labelledby="print-footer-title">
          <CardHeader>
            <CardTitle id="print-footer-title">{t("printLayout.footer")}</CardTitle>
          </CardHeader>
          <Choice
            legend={t("printLayout.footerAccounts")}
            name="footer_accounts"
            value={layout.footer_accounts}
            options={(["all", "invoice_currency"] as const).map((value) => [
              value,
              t(`printLayout.footerAccounts.${value}`),
            ])}
            onChange={(footer_accounts) => {
              change({ footer_accounts });
            }}
          />
          <p className="text-sm text-muted-foreground">{t("printLayout.footerHint")}</p>
        </Card>
        <Card aria-labelledby="print-e-invoice-title">
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
        <FormAlert message={save.isError ? errorMessage(save.error) : null} />
        <div className="flex flex-wrap items-center gap-3">
          <Button
            disabled={!dirty || save.isPending}
            onClick={() => {
              save.mutate(layout, {
                onSuccess: () => toast.success(t("common.saved")),
              });
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
      <div className="flex min-w-0 flex-col gap-2 xl:sticky xl:top-4 xl:self-start">
        <p className="text-sm text-muted-foreground">{t("printLayout.previewHint")}</p>
        <FormAlert message={preview.isError ? errorMessage(preview.error) : null} />
        <PaperPreview
          html={preview.data}
          title={t("printLayout.preview")}
          busy={preview.isFetching}
          className="max-w-3xl"
        />
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
