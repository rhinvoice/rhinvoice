import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { ChevronRightIcon, Trash2Icon } from "lucide-react";
import { useId, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";

import { ExternalLink } from "@/components/external-link";
import { useI18n } from "@/components/i18n/use-i18n";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Autocomplete } from "@/components/ui/autocomplete";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useRunOnce, useSubmitOnce } from "@/components/use-run-once";
import { FormAlert } from "@/features/shared/form-alert";
import { applyServerErrors } from "@/features/shared/server-errors";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { useUnsavedChanges } from "@/features/shared/use-unsaved-changes";
import {
  unitCodesQuery,
  useRemoveUnit,
  useSaveUnit,
  type Unit,
  type UnitCode,
} from "@/features/units/api";
import {
  codeOf,
  codeSuggestions,
  codeText,
  emptyUnit,
  formToRequest,
  hasTranslations,
  unitFieldFor,
  unitSchema,
  unitToForm,
  type UnitFormValues,
} from "@/features/units/unit-form-model";
import { docsUrl } from "@/lib/about";

/** The docs page that explains units and their codes. */
const DOCS_PAGE = "invoices/units";

/**
 * Add or edit a unit (ADR 0046, variant 2A): the label documents print, a description for
 * the user, the code for the e-invoice; labels for other languages on demand.
 */
export function UnitDialog({
  unit,
  isLast,
  onClose,
}: {
  readonly unit: Unit | null;
  /** The only unit offered: it cannot be removed. */
  readonly isLast: boolean;
  readonly onClose: () => void;
}) {
  const { t, locale } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveUnit(unit?.id ?? null);
  const defaultValues = unit === null ? emptyUnit() : unitToForm(unit);
  const form = useForm<UnitFormValues>({
    resolver: zodResolver(unitSchema(t, locale)),
    mode: "onTouched",
    defaultValues,
  });
  const { errors, isDirty } = form.formState;
  useUnsavedChanges(isDirty);
  const translationsId = useId();
  const [translations, setTranslations] = useState(hasTranslations(defaultValues));

  const submit = form.handleSubmit(async (values) => {
    try {
      await save.mutateAsync(formToRequest(values));
      toast.success(t("units.saved", { label: values.label }));
      once.finish();
      onClose();
    } catch (caught) {
      const attached = applyServerErrors(caught, form.setError, t, unitFieldFor);
      if (!attached) form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
    }
  });
  const once = useSubmitOnce(submit);

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{unit === null ? t("units.addTitle") : t("units.editTitle")}</DialogTitle>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={once.submit} noValidate>
          <FormAlert message={errors.root?.message ?? null} />
          <Field
            label={t("units.label")}
            description={t("units.labelHint")}
            error={errors.label?.message}
          >
            <Input id="unit-label" autoComplete="off" {...form.register("label")} />
          </Field>
          <Field
            label={t("units.descriptionLabel")}
            description={t("units.descriptionHint")}
            error={errors.description?.message}
            optionalLabel={t("common.optional")}
          >
            <Input id="unit-description" autoComplete="off" {...form.register("description")} />
          </Field>
          <Controller
            control={form.control}
            name="code"
            render={({ field }) => (
              <CodeField
                code={field.value}
                error={errors.code?.message}
                onChange={(code) => {
                  field.onChange(code);
                }}
                onBlur={field.onBlur}
              />
            )}
          />
          <div className="flex flex-col gap-3">
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto justify-start px-0 text-left whitespace-normal"
              aria-expanded={translations}
              aria-controls={translationsId}
              onClick={() => {
                setTranslations(!translations);
              }}
            >
              <ChevronRightIcon
                aria-hidden="true"
                className={translations ? "rotate-90 transition-transform" : "transition-transform"}
              />
              {t("units.translations")}
            </Button>
            {translations ? (
              <div id={translationsId} className="flex flex-col gap-3">
                <p className="text-sm text-muted-foreground">{t("units.translationsHint")}</p>
                <div className="grid gap-3 sm:grid-cols-3">
                  {(["en", "fr", "it"] as const).map((language) => (
                    <Field
                      key={language}
                      label={t(`units.label_${language}`)}
                      error={errors[`label_${language}`]?.message}
                      optionalLabel={t("common.optional")}
                    >
                      <Input
                        id={`unit-label_${language}`}
                        autoComplete="off"
                        {...form.register(`label_${language}`)}
                      />
                    </Field>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
          <DialogFooter className="sm:items-center">
            {unit === null ? null : <RemoveUnit unit={unit} isLast={isLast} onRemoved={onClose} />}
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" busy={once.busy}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The code of the EN 16931 list, searched by code or name; the hint links the docs. */
function CodeField({
  code,
  error,
  onChange,
  onBlur,
}: {
  readonly code: string;
  readonly error: string | undefined;
  readonly onChange: (code: string) => void;
  readonly onBlur: () => void;
}) {
  const { t, locale } = useI18n();
  const codes = useQuery(unitCodesQuery).data;
  const named = (value: string) => {
    const found = codes?.find((candidate) => candidate.code === value);
    return found === undefined ? value : codeText(found);
  };
  // What the field shows; the form keeps the code. The name follows once the list is there.
  const [typed, setTyped] = useState<string | null>(null);
  const text = typed ?? named(code);
  return (
    <div className="flex flex-col gap-1.5">
      <Field label={t("units.code")} description={t("units.codeHint")} error={error}>
        <Autocomplete<UnitCode>
          id="unit-code"
          value={text}
          onValueChange={(value) => {
            setTyped(value);
            onChange(codeOf(value, codes ?? []));
          }}
          options={codeSuggestions(codes ?? [], text)}
          optionKey={(option) => option.code}
          renderOption={(option) => (
            <span className="flex items-baseline gap-2">
              <span className="font-mono text-xs font-semibold">{option.code}</span>
              <span>{option.name}</span>
            </span>
          )}
          onSelect={(option) => {
            setTyped(codeText(option));
            onChange(option.code);
          }}
          onBlur={onBlur}
          listLabel={t("units.codes")}
          countLabel={(count) => t("common.results", { count })}
          emptyText={t("units.codeNone")}
          minLength={0}
        />
      </Field>
      <ExternalLink
        href={docsUrl(DOCS_PAGE, locale)}
        className="min-h-6 w-fit text-sm text-primary"
      >
        {t("units.codeDocs")}
      </ExternalLink>
    </div>
  );
}

/** One action: a unit nothing uses is deleted, one in use is hidden (the toast says which). */
function RemoveUnit({
  unit,
  isLast,
  onRemoved,
}: {
  readonly unit: Unit;
  readonly isLast: boolean;
  readonly onRemoved: () => void;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const remove = useRemoveUnit();
  const once = useRunOnce();
  const [asking, setAsking] = useState(false);

  return (
    <div className="flex flex-col gap-1 sm:mr-auto">
      <Button
        type="button"
        variant="ghost"
        className="w-fit text-destructive hover:bg-destructive/10 hover:text-destructive"
        disabled={isLast}
        onClick={() => {
          setAsking(true);
        }}
      >
        <Trash2Icon aria-hidden="true" />
        {t("units.remove")}
      </Button>
      {isLast ? <p className="text-xs text-muted-foreground">{t("units.lastVisible")}</p> : null}
      <AlertDialog open={asking} onOpenChange={setAsking}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("units.removeTitle", { label: unit.label })}</AlertDialogTitle>
            <AlertDialogDescription>
              {unit.in_use ? t("units.removeInUse") : t("units.removeUnused")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              destructive
              onClick={() =>
                once.run(() =>
                  remove.mutateAsync(unit.id).then(
                    ({ removal }) => {
                      toast.success(t(`units.removed.${removal}`, { label: unit.label }));
                      onRemoved();
                    },
                    (caught: unknown) => {
                      toast.error(errorMessage(caught));
                    },
                  ),
                )
              }
            >
              {t("units.remove")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
