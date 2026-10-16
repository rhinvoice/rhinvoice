import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  dunningLevelsQuery,
  useSaveDunningLevels,
  type DunningLevel,
} from "@/features/dunning/api";
import {
  levelProblems,
  toInput,
  toRequest,
  type LevelField,
  type LevelInput,
  type LevelProblem,
} from "@/features/dunning/dunning-levels-model";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";

/** The three dunning levels: when each is due, the new deadline, the fee and the texts. */
export function DunningSettings() {
  const query = useQuery(dunningLevelsQuery);
  if (query.data === undefined) {
    return query.isPending ? <Skeleton className="h-96 max-w-3xl" /> : null;
  }
  return <DunningForm saved={query.data} />;
}

function DunningForm({ saved }: { readonly saved: DunningLevel[] }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveDunningLevels();
  const [levels, setLevels] = useState(() => saved.map(toInput));
  const [checked, setChecked] = useState(false);
  const problems = checked ? levelProblems(levels) : new Map<string, LevelProblem>();
  const error = (index: number, field: LevelField) => {
    const problem = problems.get(`${String(index)}.${field}`);
    return problem === undefined ? undefined : t(`dunning.problem.${problem}`);
  };
  const change = (index: number, patch: Partial<LevelInput>) => {
    setLevels((current) =>
      current.map((level, position) => (position === index ? { ...level, ...patch } : level)),
    );
  };
  return (
    <form
      className="flex max-w-3xl flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        setChecked(true);
        if (levelProblems(levels).size > 0) return;
        save.mutate(levels.map(toRequest), {
          onSuccess: (stored) => {
            setLevels(stored.map(toInput));
            toast.success(t("common.saved"));
          },
        });
      }}
    >
      <div>
        <h2 className="text-lg font-semibold">{t("dunning.settingsTitle")}</h2>
        <p className="text-sm text-muted-foreground">{t("dunning.settingsDescription")}</p>
      </div>
      <FormAlert
        message={
          problems.size > 0 ? t("dunning.problems") : save.isError ? errorMessage(save.error) : null
        }
      />
      {levels.map((level, index) => {
        const name = t(`dunning.level.${String(level.level) as "1" | "2" | "3"}`);
        const id = (field: string) => `dunning-${String(level.level)}-${field}`;
        return (
          <Card key={level.level} aria-labelledby={id("title")}>
            <CardHeader>
              <h3 id={id("title")} className="text-base font-semibold">
                {name}
              </h3>
            </CardHeader>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field
                label={index === 0 ? t("dunning.daysAfterInvoice") : t("dunning.daysAfterReminder")}
              >
                <Input
                  id={id("days")}
                  inputMode="numeric"
                  className="tabular-nums"
                  value={level.days_after_due}
                  onChange={(event) => {
                    change(index, { days_after_due: event.target.value });
                  }}
                />
              </Field>
              <Field label={t("dunning.paymentDays")} error={error(index, "payment_days")}>
                <Input
                  id={id("payment")}
                  inputMode="numeric"
                  className="tabular-nums"
                  value={level.payment_days}
                  onChange={(event) => {
                    change(index, { payment_days: event.target.value });
                  }}
                />
              </Field>
              <Field
                label={t("dunning.fee")}
                description={t("dunning.feeHint")}
                error={error(index, "fee")}
              >
                <Input
                  id={id("fee")}
                  inputMode="decimal"
                  className="tabular-nums"
                  value={level.fee}
                  onChange={(event) => {
                    change(index, { fee: event.target.value });
                  }}
                />
              </Field>
            </div>
            <Field
              label={t("dunning.textDe")}
              description={t("dunning.textHint")}
              error={error(index, "text_de")}
            >
              <Textarea
                id={id("text-de")}
                rows={3}
                value={level.text_de}
                onChange={(event) => {
                  change(index, { text_de: event.target.value });
                }}
              />
            </Field>
            <Field label={t("dunning.textEn")} error={error(index, "text_en")}>
              <Textarea
                id={id("text-en")}
                rows={3}
                value={level.text_en}
                onChange={(event) => {
                  change(index, { text_en: event.target.value });
                }}
              />
            </Field>
            <Field label={t("dunning.textFr")} error={error(index, "text_fr")}>
              <Textarea
                id={id("text-fr")}
                rows={3}
                lang="fr"
                value={level.text_fr}
                onChange={(event) => {
                  change(index, { text_fr: event.target.value });
                }}
              />
            </Field>
            <Field label={t("dunning.textIt")} error={error(index, "text_it")}>
              <Textarea
                id={id("text-it")}
                rows={3}
                lang="it"
                value={level.text_it}
                onChange={(event) => {
                  change(index, { text_it: event.target.value });
                }}
              />
            </Field>
          </Card>
        );
      })}
      <div>
        <Button type="submit" disabled={save.isPending}>
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}
