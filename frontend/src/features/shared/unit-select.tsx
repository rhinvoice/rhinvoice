import type { ComponentProps } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { NativeSelect } from "@/components/ui/native-select";
import { unitOptions } from "@/features/shared/unit-model";
import type { Unit } from "@/features/shared/units-api";

interface UnitSelectProps extends Omit<
  ComponentProps<"select">,
  "value" | "onChange" | "children"
> {
  /** The chosen unit's id; "" for none. */
  readonly value: string;
  readonly onChange: (value: string) => void;
  /** The company's units; undefined while they load. */
  readonly units: readonly Unit[] | undefined;
  /** Lines may have no unit; articles always have one. */
  readonly allowNone?: boolean;
}

/**
 * The unit of a line, an article or a plan (ADR 0046): the company's units in its order;
 * a hidden one only where it is chosen already, marked as such.
 */
export function UnitSelect({
  value,
  onChange,
  units,
  allowNone = false,
  disabled,
  ...props
}: UnitSelectProps) {
  const { t } = useI18n();
  return (
    <NativeSelect
      value={value}
      // The choice shows once the units are there.
      disabled={disabled === true || units === undefined}
      onChange={(event) => {
        onChange(event.target.value);
      }}
      {...props}
    >
      {allowNone ? <option value="">{t("common.none")}</option> : null}
      {unitOptions(units ?? [], value).map((option) => (
        <option key={option.value} value={option.value}>
          {option.hidden ? t("units.labelHidden", { label: option.label }) : option.label}
        </option>
      ))}
    </NativeSelect>
  );
}
