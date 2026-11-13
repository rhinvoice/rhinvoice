import type { ComponentProps } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { NativeSelect } from "@/components/ui/native-select";
import { passThroughLabel, type CountryProfile } from "@/features/shared/country-profile-model";
import { resolvedChoice, taxOptions, type Percents } from "@/features/shared/tax-rate-model";
import type { TaxRate } from "@/features/shared/tax-rates-api";

interface TaxRateSelectProps extends Omit<
  ComponentProps<"select">,
  "value" | "onChange" | "children"
> {
  /** The choice: a rate id, PASS_THROUGH, or "" for the default rate. */
  readonly value: string;
  readonly onChange: (value: string) => void;
  /** The company's rates; undefined while they load. */
  readonly rates: readonly TaxRate[] | undefined;
  /** Percentages on the date of supply, by rate id. */
  readonly percents: Percents;
  /** Names the country's tax on pass-through items ("ohne MWST"). */
  readonly profile: CountryProfile | null | undefined;
}

/**
 * The tax choice of a line or an article (ADR 0044, variant 3B): the company's rates as
 * "Name – 8.1 %", grouped into taxable and without tax, the pass-through item last.
 */
export function TaxRateSelect({
  value,
  onChange,
  rates,
  percents,
  profile,
  disabled,
  ...props
}: TaxRateSelectProps) {
  const { t, locale } = useI18n();
  const loaded = rates ?? [];
  const chosen = resolvedChoice(loaded, value);
  const options = taxOptions(
    loaded,
    value,
    percents,
    passThroughLabel(profile, locale, t),
    locale,
    t,
  );
  return (
    <NativeSelect
      value={chosen ?? ""}
      // The choice shows once the rates are there.
      disabled={disabled === true || rates === undefined}
      onChange={(event) => {
        onChange(event.target.value);
      }}
      {...props}
    >
      {/* Without a taxable rate there is no default: the choice is up to the user. */}
      {chosen === null ? (
        <option value="" disabled>
          {t("taxRates.choose")}
        </option>
      ) : null}
      {options.taxed.length === 0 ? null : (
        <optgroup label={t("taxRates.groupTaxed")}>
          {options.taxed.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </optgroup>
      )}
      <optgroup label={t("taxRates.groupUntaxed")}>
        {options.untaxed.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </optgroup>
    </NativeSelect>
  );
}
