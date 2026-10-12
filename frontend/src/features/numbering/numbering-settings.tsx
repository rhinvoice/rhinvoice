import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useDebouncedValue } from "@/components/use-debounced-value";
import {
  sequencePreviewQuery,
  sequencesQuery,
  useSaveSequence,
  type Sequence,
} from "@/features/numbering/api";
import { FormAlert } from "@/features/shared/form-alert";
import { applyServerErrors } from "@/features/shared/server-errors";
import { useErrorMessage } from "@/features/shared/use-error-message";
import type { T } from "@/lib/i18n";
import { patternProblem } from "@/lib/validation/number-pattern";

const MAX_COUNTER = 999_999_999_999;

function sequenceSchema(t: T) {
  const counter = z
    .string()
    .trim()
    .regex(/^\d{1,12}$/, t("validation.positiveInteger"))
    .refine(
      (value) => Number(value) >= 1 && Number(value) <= MAX_COUNTER,
      t("validation.positiveInteger"),
    );
  return z
    .object({
      pattern: z.string().trim(),
      next_value: counter,
      start_value: counter,
      yearly_reset: z.boolean(),
    })
    .superRefine((values, context) => {
      const problem = patternProblem(values.pattern, values.yearly_reset);
      if (problem !== null) {
        context.addIssue({
          code: "custom",
          path: ["pattern"],
          message: t(`numbering.problem.${problem}`),
        });
      }
    });
}

type SequenceFormValues = z.infer<ReturnType<typeof sequenceSchema>>;

/** Shape of the debounced form snapshot (unvalidated input values). */
const SNAPSHOT = z.object({
  pattern: z.string(),
  next_value: z.string(),
  start_value: z.string(),
  yearly_reset: z.boolean(),
});

export function NumberingSettings() {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const sequences = useQuery(sequencesQuery);
  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold">{t("numbering.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("numbering.description")}</p>
      </div>
      <FormAlert message={sequences.isError ? errorMessage(sequences.error) : null} />
      {sequences.data === undefined ? (
        sequences.isPending ? (
          <Skeleton className="h-48 w-full" />
        ) : null
      ) : (
        sequences.data.map((sequence) => <SequenceCard key={sequence.kind} sequence={sequence} />)
      )}
    </div>
  );
}

function SequenceCard({ sequence }: { readonly sequence: Sequence }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveSequence(sequence.kind);
  const prefix = `seq-${sequence.kind}`;
  const form = useForm<SequenceFormValues>({
    resolver: zodResolver(sequenceSchema(t)),
    mode: "onTouched",
    defaultValues: {
      pattern: sequence.pattern,
      next_value: String(sequence.next_value),
      start_value: String(sequence.start_value),
      yearly_reset: sequence.yearly_reset,
    },
  });
  const { errors, isDirty, isSubmitting } = form.formState;
  const watched = useWatch({ control: form.control });
  // Debounce a string: a fresh object on every render would restart the timer forever.
  const snapshot = useDebouncedValue(
    JSON.stringify({
      pattern: watched.pattern ?? "",
      next_value: watched.next_value ?? "",
      start_value: watched.start_value ?? "",
      yearly_reset: watched.yearly_reset ?? false,
    }),
    300,
  );
  const values = SNAPSHOT.parse(JSON.parse(snapshot));
  const body = {
    pattern: values.pattern.trim(),
    next_value: Number(values.next_value),
    start_value: Number(values.start_value),
    yearly_reset: values.yearly_reset,
  };
  const validation = sequenceSchema(t).safeParse(values);
  const valid = validation.success;
  const livePatternError = validation.success
    ? undefined
    : validation.error.issues.find((issue) => issue.path[0] === "pattern")?.message;
  const preview = useQuery({
    ...sequencePreviewQuery(sequence.kind, body),
    enabled: valid && isDirty,
  });
  const nextNumber = !isDirty ? sequence.next_number : preview.data?.next_number;
  const previewError = isDirty && preview.isError ? (errorMessage(preview.error) ?? "") : null;

  const submit = form.handleSubmit(async (formValues) => {
    try {
      const saved = await save.mutateAsync({
        pattern: formValues.pattern,
        next_value: Number(formValues.next_value),
        start_value: Number(formValues.start_value),
        yearly_reset: formValues.yearly_reset,
      });
      form.reset({
        pattern: saved.pattern,
        next_value: String(saved.next_value),
        start_value: String(saved.start_value),
        yearly_reset: saved.yearly_reset,
      });
      toast.success(t("numbering.saved"));
    } catch (caught) {
      if (
        !applyServerErrors(caught, form.setError, t, (field) =>
          field === "pattern" ? "pattern" : null,
        )
      ) {
        form.setError("root", { type: "server", message: errorMessage(caught) ?? "" });
      }
    }
  });

  return (
    <Card aria-labelledby={`${prefix}-title`}>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle id={`${prefix}-title`}>{t(`numbering.kind.${sequence.kind}`)}</CardTitle>
        <p className="text-sm" aria-live="polite">
          <span className="text-muted-foreground">{t("numbering.preview")}: </span>
          <span className="font-mono font-medium tabular-nums">{nextNumber ?? "…"}</span>
        </p>
      </CardHeader>
      <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)} noValidate>
        <FormAlert message={errors.root?.message ?? previewError} />
        <div className="grid gap-4 sm:grid-cols-[1fr_10rem]">
          <Field
            label={t("numbering.pattern")}
            description={t("numbering.patternHint")}
            error={errors.pattern?.message ?? (isDirty ? livePatternError : undefined)}
          >
            <Input
              id={`${prefix}-pattern`}
              className="font-mono"
              spellCheck={false}
              {...form.register("pattern")}
            />
          </Field>
          <Field
            label={t("numbering.nextValue")}
            description={t("numbering.nextValueHint")}
            error={errors.next_value?.message}
          >
            <Input
              id={`${prefix}-next`}
              inputMode="numeric"
              className="tabular-nums"
              {...form.register("next_value")}
            />
          </Field>
        </div>
        <Controller
          control={form.control}
          name="yearly_reset"
          render={({ field }) => (
            <div className="flex items-center justify-between gap-4">
              <Label htmlFor={`${prefix}-reset`}>{t("numbering.yearlyReset")}</Label>
              <Switch
                id={`${prefix}-reset`}
                checked={field.value}
                onCheckedChange={field.onChange}
              />
            </div>
          )}
        />
        {watched.yearly_reset === true ? (
          <Field label={t("numbering.startValue")} error={errors.start_value?.message}>
            <Input
              id={`${prefix}-start`}
              inputMode="numeric"
              className="tabular-nums sm:max-w-40"
              {...form.register("start_value")}
            />
          </Field>
        ) : null}
        <div className="flex justify-end">
          <Button
            type="submit"
            variant={isDirty ? "default" : "outline"}
            disabled={!isDirty || isSubmitting}
          >
            {t("common.save")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
