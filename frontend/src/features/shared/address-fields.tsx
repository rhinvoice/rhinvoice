import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import type { FieldErrors, FieldValues, Path, UseFormRegister } from "react-hook-form";

import { useI18n } from "@/components/i18n/use-i18n";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { countriesQuery } from "@/features/shared/reference-api";
import { countryOptions } from "@/lib/countries";

export interface AddressFieldNames<V extends FieldValues> {
  readonly street: Path<V>;
  readonly house_number: Path<V>;
  readonly supplement: Path<V>;
  readonly postal_code: Path<V>;
  readonly city: Path<V>;
  readonly country: Path<V>;
}

interface AddressFieldsProps<V extends FieldValues> {
  readonly names: AddressFieldNames<V>;
  readonly register: UseFormRegister<V>;
  readonly errors: FieldErrors<V>;
  /** Restricts the country list (e.g. the company must be in CH, LI, DE or AT). */
  readonly countries?: readonly string[];
}

function message<V extends FieldValues>(errors: FieldErrors<V>, name: Path<V>): string | undefined {
  const error = errors[name];
  return typeof error?.message === "string" ? error.message : undefined;
}

/** Structured address as required by the Swiss QR-bill (street and number separate). */
export function AddressFields<V extends FieldValues>({
  names,
  register,
  errors,
  countries,
}: AddressFieldsProps<V>) {
  const { t, locale } = useI18n();
  const allCountries = useQuery({ ...countriesQuery, enabled: countries === undefined });
  const options = useMemo(
    () => countryOptions(countries ?? allCountries.data ?? ["CH", "LI", "DE", "AT"], locale),
    [countries, allCountries.data, locale],
  );
  return (
    <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
      <Field
        label={t("address.street")}
        error={message(errors, names.street)}
        optionalLabel={t("common.optional")}
      >
        <Input id={names.street} autoComplete="address-line1" {...register(names.street)} />
      </Field>
      <Field
        label={t("address.houseNumber")}
        error={message(errors, names.house_number)}
        optionalLabel={t("common.optional")}
      >
        <Input id={names.house_number} {...register(names.house_number)} />
      </Field>
      <Field
        className="sm:col-span-2"
        label={t("address.supplement")}
        description={t("address.supplementHint")}
        error={message(errors, names.supplement)}
        optionalLabel={t("common.optional")}
      >
        <Input id={names.supplement} autoComplete="address-line2" {...register(names.supplement)} />
      </Field>
      <div className="grid gap-4 sm:col-span-2 sm:grid-cols-[8rem_1fr]">
        <Field label={t("address.postalCode")} error={message(errors, names.postal_code)}>
          <Input
            id={names.postal_code}
            autoComplete="postal-code"
            {...register(names.postal_code)}
          />
        </Field>
        <Field label={t("address.city")} error={message(errors, names.city)}>
          <Input id={names.city} autoComplete="address-level2" {...register(names.city)} />
        </Field>
      </div>
      <Field
        className="sm:col-span-2"
        label={t("address.country")}
        error={message(errors, names.country)}
      >
        <NativeSelect id={names.country} autoComplete="country" {...register(names.country)}>
          {options.map((option) => (
            <option key={option.code} value={option.code}>
              {option.name}
            </option>
          ))}
        </NativeSelect>
      </Field>
    </div>
  );
}
