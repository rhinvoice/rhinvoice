import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CheckIcon, LockIcon, PlusIcon } from "lucide-react";
import { useFormContext, useWatch } from "react-hook-form";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { fieldId, type DocumentFormValues } from "@/features/documents/document-form-model";
import {
  containsTemplate,
  templatesFor,
  toggleTemplate,
} from "@/features/documents/document-texts";
import { textTemplatesQuery, type TextKind } from "@/features/shared/texts-api";

interface DocumentTextFieldsProps {
  readonly type: "invoice" | "quote";
  /** The legal notice of the tax treatment; undefined until it is known. */
  readonly notice: string | undefined;
}

/** Intro, payment terms and closing, filled from the text templates of the settings. */
export function DocumentTextFields({ type, notice }: DocumentTextFieldsProps) {
  const { t } = useI18n();
  const { control, register, setValue, formState } = useFormContext<DocumentFormValues>();
  const templates = useQuery(textTemplatesQuery).data ?? [];
  const language = useWatch({ control, name: "language" });
  const payment = useWatch({ control, name: "payment_text" });
  const error = (name: "intro_text" | "payment_text" | "closing_text") =>
    formState.errors[name]?.message;
  const set = (name: "intro_text" | "payment_text" | "closing_text", value: string) => {
    setValue(name, value, { shouldDirty: true, shouldValidate: true });
  };

  const picker = (kind: TextKind, name: "intro_text" | "closing_text") => {
    const options = templatesFor(templates, kind, type, language);
    if (options.length === 0) return null;
    return (
      <NativeSelect
        aria-label={t("documents.insertTemplate")}
        value=""
        onChange={(event) => {
          const chosen = options.find((option) => option.id === event.target.value);
          if (chosen !== undefined) set(name, chosen.text);
        }}
      >
        <option value="">{t("documents.insertTemplate")}</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </NativeSelect>
    );
  };
  const payments = templatesFor(templates, "payment", type, language);

  return (
    <div className="flex flex-col gap-5">
      <Field
        label={t("documents.introText")}
        error={error("intro_text")}
        optionalLabel={t("common.optional")}
      >
        <Textarea id={fieldId("intro_text")} rows={2} {...register("intro_text")} />
      </Field>
      {picker("intro", "intro_text")}

      {type === "invoice" || payments.length > 0 ? (
        <div className="flex flex-col gap-2">
          <Field
            label={t("documents.paymentText")}
            description={t("documents.placeholdersHint")}
            error={error("payment_text")}
            optionalLabel={t("common.optional")}
          >
            <Textarea id={fieldId("payment_text")} rows={3} {...register("payment_text")} />
          </Field>
          {payments.length === 0 ? null : (
            <div
              role="group"
              aria-label={t("documents.paymentTemplates")}
              className="flex flex-wrap gap-1.5"
            >
              {payments.map((template) => {
                const active = containsTemplate(payment, template);
                return (
                  <Button
                    key={template.id}
                    type="button"
                    size="sm"
                    variant={active ? "secondary" : "outline"}
                    className={
                      active ? "rounded-full bg-accent text-accent-foreground" : "rounded-full"
                    }
                    aria-pressed={active}
                    onClick={() => {
                      set("payment_text", toggleTemplate(payment, template, payments));
                    }}
                  >
                    {active ? <CheckIcon aria-hidden="true" /> : <PlusIcon aria-hidden="true" />}
                    {template.name}
                  </Button>
                );
              })}
            </div>
          )}
        </div>
      ) : null}

      <Field
        label={t("documents.closingText")}
        error={error("closing_text")}
        optionalLabel={t("common.optional")}
      >
        <Textarea id={fieldId("closing_text")} rows={2} {...register("closing_text")} />
      </Field>
      {picker("closing", "closing_text")}

      {notice === undefined || notice === "" ? null : (
        <p className="flex items-start gap-2 rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          <LockIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-medium text-foreground">{t("documents.noticeAuto")}</span>{" "}
            {notice}
          </span>
        </p>
      )}
      <Link
        to="/settings"
        search={{ tab: "texts" }}
        className="inline-flex min-h-6 w-fit items-center text-sm text-primary underline-offset-4 hover:underline"
      >
        {t("documents.manageTemplates")}
      </Link>
    </div>
  );
}
