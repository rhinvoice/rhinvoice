import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/lib/api-error";
import { errorMessageKey, type T } from "@/lib/i18n";

/**
 * Show validation and conflict errors from the API at the matching form fields.
 * ``fieldFor`` maps API detail keys (e.g. "address.city") to form field names.
 * Returns true when at least one error could be attached to a field.
 */
export function applyServerErrors<V extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<V>,
  t: T,
  fieldFor: (apiField: string) => Path<V> | null,
): boolean {
  if (!(error instanceof ApiError) || (error.status !== 422 && error.status !== 409)) {
    return false;
  }
  let attached = false;
  for (const [apiField, message] of Object.entries(error.details)) {
    const field = fieldFor(apiField);
    if (field === null) continue;
    // Business rules with a known code are translated; others show the server text.
    const known = errorMessageKey(error.code);
    const text =
      error.code === "conflict" && apiField === "number"
        ? t("validation.numberTaken")
        : known === "error.generic"
          ? t("validation.server", { message })
          : t(known);
    setError(field, { type: "server", message: text }, { shouldFocus: !attached });
    attached = true;
  }
  return attached;
}
